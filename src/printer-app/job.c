/*
 * This file is part of phomemo-printer-app.
 * Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
 *
 * phomemo-printer-app is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * phomemo-printer-app is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with phomemo-printer-app.  If not, see <https://www.gnu.org/licenses/>.
 */

// Raster job pipeline: streams PAPPL's raster lines to the bridge as pages.
//
// PAPPL drives one job at a time per printer: rstartjob, then per page
// rstartpage, rwriteline for every row and rendpage, then rendjob. The
// bridge connection belongs to the open device; the per-job state here
// buffers rows into "lines" messages and tracks the page in progress.

#include "phomemo.h"
#include "bridge.h"

#include <stdlib.h>
#include <string.h>

#define ROWS_PER_MESSAGE 64

#define WAITING_REASONS                                                        \
  (PAPPL_PREASON_MEDIA_NEEDED | PAPPL_PREASON_MEDIA_EMPTY |                    \
   PAPPL_PREASON_COVER_OPEN | PAPPL_PREASON_OTHER | PAPPL_PREASON_OFFLINE)

typedef struct
{
  pappl_job_t *job;
  pappl_printer_t *printer;
  phomemo_bridge_t *bridge;
  unsigned char *buffer;  // rows not yet sent
  size_t row_bytes;
  unsigned buffered;      // rows in buffer
  bool page_open;         // page_begin accepted, page_end not yet sent
  bool abort_sent;        // abort sent for the pending command
  bool failed;            // a bridge call failed; error holds the text
  char error[256];
} phomemo_job_t;

// Sends abort once when the job has been cancelled.
static void
abort_if_cancelled(phomemo_job_t *pj)
{
  if (pj->abort_sent || !papplJobIsCanceled(pj->job))
    return;

  cJSON *request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "abort");
  phomemo_bridge_send(pj->bridge, request, NULL, 0, NULL, 0);
  cJSON_Delete(request);
  pj->abort_sent = true;
}

// Handles events pushed while a command is pending, and the periodic
// NULL tick.
static void
job_event_cb(cJSON *event, void *data)
{
  phomemo_job_t *pj = data;

  if (event)
  {
    cJSON *name = cJSON_GetObjectItem(event, "event");
    cJSON *reason = cJSON_GetObjectItem(event, "reason");
    cJSON *percent = cJSON_GetObjectItem(event, "percent");

    if (cJSON_IsString(name) && !strcmp(name->valuestring, "waiting") &&
        cJSON_IsString(reason))
    {
      const char *why = reason->valuestring;
      pappl_preason_t others = WAITING_REASONS & ~PAPPL_PREASON_MEDIA_NEEDED;

      if (!strcmp(why, "connecting"))
      {
        papplJobSetMessage(pj->job, "Connecting to the printer.");
      }
      else if (!strcmp(why, "printer-off"))
      {
        papplPrinterSetReasons(pj->printer, PAPPL_PREASON_OFFLINE,
                               others & ~PAPPL_PREASON_OFFLINE);
        papplJobSetMessage(pj->job,
                           "Printer off, out of range or in use elsewhere; "
                           "switch it on.");
      }
      else if (!strcmp(why, "adapter-off"))
      {
        papplPrinterSetReasons(pj->printer, PAPPL_PREASON_OTHER,
                               others & ~PAPPL_PREASON_OTHER);
        papplJobSetMessage(pj->job, "Turn on Bluetooth.");
      }
      else if (!strcmp(why, "lid-open"))
      {
        papplPrinterSetReasons(pj->printer, PAPPL_PREASON_COVER_OPEN,
                               others & ~PAPPL_PREASON_COVER_OPEN);
        papplJobSetMessage(pj->job, "Close the lid.");
      }
      else if (!strcmp(why, "short-sheet"))
      {
        papplPrinterSetReasons(pj->printer, PAPPL_PREASON_MEDIA_EMPTY,
                               others & ~PAPPL_PREASON_MEDIA_EMPTY);
        papplJobSetMessage(pj->job, "Sheet too short; insert a longer one.");
      }
      else
      {
        papplPrinterSetReasons(pj->printer, PAPPL_PREASON_MEDIA_EMPTY,
                               others & ~PAPPL_PREASON_MEDIA_EMPTY);
        papplJobSetMessage(pj->job, "Insert a sheet.");
      }
    }
    else if (cJSON_IsString(name) && !strcmp(name->valuestring, "progress") &&
             cJSON_IsNumber(percent))
    {
      papplLogJob(pj->job, PAPPL_LOGLEVEL_DEBUG, "Transfer %d%%",
                  percent->valueint);
      papplJobSetMessage(pj->job, "Printing %d%%.", percent->valueint);
    }
  }

  abort_if_cancelled(pj);
}

// Records a failed bridge call for rendpage to report.
static void
fail(phomemo_job_t *pj, const char *err)
{
  if (!pj->failed)
  {
    pj->failed = true;
    snprintf(pj->error, sizeof(pj->error), "%s", err);
  }
}

// Sends the buffered rows as one lines message.
static bool
flush_rows(phomemo_job_t *pj)
{
  char err[256];

  if (pj->buffered == 0 || pj->failed)
    return !pj->failed;

  cJSON *request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "lines");
  cJSON_AddNumberToObject(request, "count", pj->buffered);
  cJSON *reply = phomemo_bridge_call(pj->bridge, request, pj->buffer,
                                     pj->buffered * pj->row_bytes, NULL, NULL,
                                     err, sizeof(err));
  cJSON_Delete(request);
  pj->buffered = 0;
  if (!reply)
  {
    fail(pj, err);
    return false;
  }
  cJSON_Delete(reply);
  return true;
}

bool
phomemo_rstartjob_cb(pappl_job_t *job, pappl_pr_options_t *options,
                     pappl_device_t *device)
{
  char err[256];

  phomemo_bridge_t *bridge = phomemo_device_bridge(device, err, sizeof(err));
  if (!bridge)
  {
    papplJobSetReasons(job, PAPPL_JREASON_ERRORS_DETECTED, 0);
    papplJobSetMessage(job, "Unable to reach phomemo-bridge: %s", err);
    return false;
  }

  phomemo_job_t *pj = calloc(1, sizeof(*pj));
  if (!pj)
    return false;
  pj->job = job;
  pj->printer = papplJobGetPrinter(job);
  pj->bridge = bridge;
  papplJobSetData(job, pj);
  return true;
}

bool
phomemo_rstartpage_cb(pappl_job_t *job, pappl_pr_options_t *options,
                      pappl_device_t *device, unsigned page)
{
  phomemo_job_t *pj = papplJobGetData(job);
  char err[256];

  if (!pj)
    return false;

  pj->bridge = phomemo_device_bridge(device, err, sizeof(err));
  if (!pj->bridge)
  {
    papplJobSetReasons(job, PAPPL_JREASON_ERRORS_DETECTED, 0);
    papplJobSetMessage(job, "Unable to reach phomemo-bridge: %s", err);
    return false;
  }

  pj->row_bytes = options->header.cupsBytesPerLine;
  unsigned char *buffer = realloc(pj->buffer, pj->row_bytes * ROWS_PER_MESSAGE);
  if (!buffer)
    return false;
  pj->buffer = buffer;
  pj->buffered = 0;
  pj->page_open = false;
  pj->abort_sent = false;
  pj->failed = false;

  papplPrinterSetReasons(pj->printer, PAPPL_PREASON_MEDIA_NEEDED, 0);
  papplJobSetMessage(job, "Waiting for the printer.");
  cJSON *request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "wait_ready");
  cJSON *reply = phomemo_bridge_call(pj->bridge, request, NULL, 0, job_event_cb,
                                     pj, err, sizeof(err));
  cJSON_Delete(request);
  papplPrinterSetReasons(pj->printer, 0, WAITING_REASONS);
  if (!reply)
  {
    if (!papplJobIsCanceled(job))
    {
      papplJobSetReasons(job, PAPPL_JREASON_ERRORS_DETECTED, 0);
      papplJobSetMessage(job, "%s", err);
    }
    return false;
  }
  cJSON_Delete(reply);

  unsigned bits = options->header.cupsBitsPerPixel;
  const char *tone =
    cupsGetOption(PHOMEMO_TONE_OPTION, options->num_vendor, options->vendor);

  request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "page_begin");
  cJSON_AddNumberToObject(request, "width", (double)(pj->row_bytes * 8 / bits));
  cJSON_AddNumberToObject(request, "length_rows", options->header.cupsHeight);
  cJSON_AddNumberToObject(request, "bits", bits);
  cJSON_AddStringToObject(request, "tone", tone ? tone : "auto");
  cJSON_AddStringToObject(request, "content",
                          phomemo_content_name(options->print_content_optimize));
  cJSON_AddStringToObject(request, "density",
                          phomemo_density_for_quality(options->print_quality));
  cJSON_AddNumberToObject(request, "media_length_mm",
                          phomemo_media_length_mm(options));
  cJSON_AddBoolToObject(request, "rotate", phomemo_should_rotate(options));
  reply = phomemo_bridge_call(pj->bridge, request, NULL, 0, NULL, NULL, err,
                              sizeof(err));
  cJSON_Delete(request);
  if (!reply)
  {
    papplJobSetReasons(job, PAPPL_JREASON_ERRORS_DETECTED, 0);
    papplJobSetMessage(job, "%s", err);
    return false;
  }
  cJSON_Delete(reply);

  papplJobSetMessage(job, "Sending page %u.", page + 1);
  pj->page_open = true;
  return true;
}

bool
phomemo_rwriteline_cb(pappl_job_t *job, pappl_pr_options_t *options,
                      pappl_device_t *device, unsigned y,
                      const unsigned char *line)
{
  phomemo_job_t *pj = papplJobGetData(job);

  if (!pj || !pj->page_open || pj->failed || papplJobIsCanceled(job))
    return true;

  memcpy(pj->buffer + pj->buffered * pj->row_bytes, line, pj->row_bytes);
  pj->buffered++;
  if (pj->buffered == ROWS_PER_MESSAGE)
    flush_rows(pj);
  return true;
}

bool
phomemo_rendpage_cb(pappl_job_t *job, pappl_pr_options_t *options,
                    pappl_device_t *device, unsigned page)
{
  phomemo_job_t *pj = papplJobGetData(job);
  char err[256];

  if (!pj || !pj->page_open)
    return false;
  pj->page_open = false;

  // A cancelled page is dropped unfinished; the bridge replaces it at the
  // next page_begin or when its session ends. The seated sheet stays in
  // the printer.
  if (papplJobIsCanceled(job))
    return true;

  if (!flush_rows(pj))
  {
    papplJobSetReasons(job, PAPPL_JREASON_ERRORS_DETECTED, 0);
    papplJobSetMessage(job, "%s", pj->error);
    return false;
  }

  cJSON *request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "page_end");
  cJSON *reply = phomemo_bridge_call(pj->bridge, request, NULL, 0, job_event_cb,
                                     pj, err, sizeof(err));
  cJSON_Delete(request);
  // The bridge may have waited for the lid or a sheet while printing the
  // page again; those reasons end with the page.
  papplPrinterSetReasons(pj->printer, 0, WAITING_REASONS);
  if (!reply)
  {
    // "cancelled" is the echo of our own abort; PAPPL already marks the
    // job canceled.
    if (strcmp(err, "cancelled"))
    {
      papplJobSetReasons(job, PAPPL_JREASON_ERRORS_DETECTED, 0);
      papplJobSetMessage(job, "%s", err);
    }
    return false;
  }
  cJSON_Delete(reply);

  papplJobSetMessage(job, "Page %u printed.", page + 1);
  return true;
}

bool
phomemo_rendjob_cb(pappl_job_t *job, pappl_pr_options_t *options,
                   pappl_device_t *device)
{
  phomemo_job_t *pj = papplJobGetData(job);
  if (pj)
  {
    free(pj->buffer);
    free(pj);
    papplJobSetData(job, NULL);
  }
  return true;
}
