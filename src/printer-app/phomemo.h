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

// Shared declarations of the Phomemo printer application.
//
// The application is a PAPPL printer application: PAPPL provides IPP,
// DNS-SD, the job queue and the web interface; this code maps PAPPL's
// driver and device callbacks onto the phomemo-bridge daemon, which owns
// the printer protocol and the BLE link.

#ifndef PHOMEMO_H
#define PHOMEMO_H

#include <pappl/pappl.h>
#include <stddef.h>

#include "bridge.h"

#define PHOMEMO_VERSION "0.1.0"
#define PHOMEMO_URI_SCHEME "phomemo"
#define PHOMEMO_TONE_OPTION "phomemo-tone"
#define PHOMEMO_MEDIA_TYPE "thermal"  // the only paper the printers take
#define PHOMEMO_LOW_BATTERY 15  // percent
#define PHOMEMO_MAX_MODELS 16
#define PHOMEMO_MAX_MEDIA 8

// A model description built into the binary by embed-models.sh from the
// repository's src/models/: model.json as a string, the icons as PNG bytes.
typedef struct
{
  const char *id;
  const char *json;
  struct
  {
    const unsigned char *data;
    size_t len;
  } icons[3];  // 48, 128 and 512 px; NULL when the model has none
} phomemo_embedded_model_t;

extern const phomemo_embedded_model_t phomemo_embedded_models[];
extern const int phomemo_num_embedded_models;

// A printer model, from an embedded description or a description directory
// (<models dir>/<id>/model.json plus icon-48/128/512.png).
typedef struct
{
  char id[32];               // lower-case identifier, also the driver name
  char make_and_model[128];  // "Phomemo M08F"
  char device_id[128];       // "MFG:Phomemo;MDL:M08F;CMD:PHOMEMO;"
  int dpi;
  int width_px;
  int head_width;     // print head width in hundredths of a millimetre
  int top_margin;     // hundredths of a millimetre
  int bottom_margin;  // hundredths of a millimetre
  int num_media;
  char media[PHOMEMO_MAX_MEDIA][64];  // PWG media names
  int default_media;                  // index into media
  // Icons in 48, 128 and 512 px: embedded PNG data, or files for
  // descriptions read from a directory.
  const unsigned char *icon_data[3];
  size_t icon_len[3];
  char icons[3][256];
} phomemo_model_t;

// Fills the model table, replacing what it held: from the description
// directories under dir, or with dir NULL from $PHOMEMO_MODELS_DIR when set
// and otherwise from the descriptions built into the binary. Returns the
// number of models read; 0 with err set when none could be read.
int phomemo_models_load(const char *dir, char *err, size_t errsize);

// The models read by phomemo_models_load, in identifier order.
int phomemo_models_count(void);
const phomemo_model_t *phomemo_model_at(int index);

// The model with this identifier, or NULL.
const phomemo_model_t *phomemo_model_find(const char *id);

// The model whose device ID equals device_id, or NULL.
const phomemo_model_t *phomemo_model_for_device_id(const char *device_id);

// Copies the model of a phomemo:// URI (its "model" query parameter) into
// buffer; false when the URI names none.
bool phomemo_uri_model(const char *device_uri, char *buffer, size_t bufsize);

// Device info for a discovered printer: the model's make and model followed
// by the last three bytes of its address without colons, e.g.
// "Phomemo M08F (DDEEFF)". PAPPL names auto-added printers after it, so each
// printer gets a distinct name.
void phomemo_device_info(const phomemo_model_t *model, const char *address,
                         char *buffer, size_t bufsize);

// Publishes the battery charge as the printer's supply level.
void phomemo_set_battery(pappl_printer_t *printer, int percent);

// Identify-Printer callback: the bridge ejects a loaded sheet and pulses
// the feed.
void phomemo_identify_cb(pappl_printer_t *printer,
                         pappl_identify_actions_t actions,
                         const char *message);

// Test page callback: the bridge renders a PNG with the device details;
// returns its path in buffer, or NULL when the bridge is unreachable.
const char *phomemo_testpage_cb(pappl_printer_t *printer, char *buffer,
                                size_t bufsize);

// Registers the phomemo:// device scheme with PAPPL. The URI host part
// is the printer's BLE address with dashes instead of colons, because a URI
// host cannot hold colons; the query names the model
// (phomemo://AA-BB-CC-DD-EE-FF?model=m08f).
void phomemo_device_add_scheme(void);

// The bridge connection of an open device, reconnected (connect plus open)
// when the daemon dropped it. NULL with err set when the daemon is not
// reachable.
phomemo_bridge_t *phomemo_device_bridge(pappl_device_t *device, char *err,
                                        size_t errsize);

// Resolves the bridge socket path: $PHOMEMO_BRIDGE_SOCKET, else
// $XDG_RUNTIME_DIR/phomemo-bridge.sock, else /run/phomemo/bridge.sock.
const char *phomemo_socket_path(char *buffer, size_t bufsize);

// Driver callback registered with PAPPL; the driver name is a model ID.
bool phomemo_driver_cb(pappl_system_t *system, const char *driver_name,
                       const char *device_uri, const char *device_id,
                       pappl_pr_driver_data_t *data, ipp_t **attrs,
                       void *cbdata);

// Printer density keyword for an IPP print-quality value.
const char *phomemo_density_for_quality(ipp_quality_t quality);

// Bridge content keyword for a print-content-optimize value.
const char *phomemo_content_name(pappl_content_t content);

// True when the page must be rotated: the medium lies with its length
// across the head (as A5 does on an A4 printer) and the page is portrait.
// head_width is in hundredths of a millimetre.
bool phomemo_should_rotate(const pappl_pr_options_t *options, int head_width);

// Media length along the feed direction in millimetres: the dimension that
// does not lie across the head (A5 on an A4 printer feeds 148 mm).
double phomemo_media_length_mm(const pappl_pr_options_t *options,
                               int head_width);

// Raster job callbacks registered in the driver data.
bool phomemo_rstartjob_cb(pappl_job_t *job, pappl_pr_options_t *options,
                          pappl_device_t *device);
bool phomemo_rstartpage_cb(pappl_job_t *job, pappl_pr_options_t *options,
                           pappl_device_t *device, unsigned page);
bool phomemo_rwriteline_cb(pappl_job_t *job, pappl_pr_options_t *options,
                           pappl_device_t *device, unsigned y,
                           const unsigned char *line);
bool phomemo_rendpage_cb(pappl_job_t *job, pappl_pr_options_t *options,
                         pappl_device_t *device, unsigned page);
bool phomemo_rendjob_cb(pappl_job_t *job, pappl_pr_options_t *options,
                        pappl_device_t *device);

// Printer status callback: refreshes printer-state-reasons while idle.
bool phomemo_status_cb(pappl_printer_t *printer);

// Picks the driver for a discovered device URI.
const char *phomemo_autoadd_cb(const char *device_info, const char *device_uri,
                               const char *device_id, void *data);

#endif // PHOMEMO_H
