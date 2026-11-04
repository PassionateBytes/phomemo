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

// The phomemo:// device scheme. A device is one bridge connection; the
// URI host part is the printer's BLE address.

#include "phomemo.h"
#include "bridge.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define URI_PREFIX PHOMEMO_URI_SCHEME "://"

typedef struct
{
  phomemo_bridge_t bridge;
  char address[64];  // BLE address sent with open
  char model[32];    // model ID sent with open; empty when the URI names none
} phomemo_device_t;

const char *
phomemo_socket_path(char *buffer, size_t bufsize)
{
  const char *env = getenv("PHOMEMO_BRIDGE_SOCKET");
  const char *runtime = getenv("XDG_RUNTIME_DIR");

  if (env && *env)
    snprintf(buffer, bufsize, "%s", env);
  else if (runtime && *runtime)
    snprintf(buffer, bufsize, "%s/phomemo-bridge.sock", runtime);
  else
    snprintf(buffer, bufsize, "/run/phomemo/bridge.sock");
  return buffer;
}

// Copies the host part of a phomemo:// URI into address as a BLE address
// (dashes become colons). Returns false when the URI has another scheme
// or no host.
static bool
parse_address(const char *device_uri, char *address, size_t size)
{
  if (!device_uri || strncmp(device_uri, URI_PREFIX, strlen(URI_PREFIX)))
    return false;

  const char *host = device_uri + strlen(URI_PREFIX);
  size_t len = strcspn(host, "/?#");
  if (len == 0 || len >= size)
    return false;

  for (size_t i = 0; i < len; i++)
    address[i] = host[i] == '-' ? ':' : host[i];
  address[len] = '\0';
  return true;
}

void
phomemo_device_info(const phomemo_model_t *model, const char *address,
                    char *buffer, size_t bufsize)
{
  size_t len = strlen(address);
  const char *tail = len > 8 ? address + len - 8 : address;
  char suffix[9];
  size_t n = 0;

  for (; *tail && n < sizeof(suffix) - 1; tail++)
    if (*tail != ':')
      suffix[n++] = *tail;
  suffix[n] = '\0';

  snprintf(buffer, bufsize, "%s (%s)", model->make_and_model, suffix);
}

// Builds the device URI for a BLE address and model (colons become dashes).
static void
format_uri(const char *address, const char *model, char *uri, size_t size)
{
  size_t prefix = strlen(URI_PREFIX);
  snprintf(uri, size, "%s%s", URI_PREFIX, address);
  for (char *p = uri + prefix; *p; p++)
    if (*p == ':')
      *p = '-';
  size_t len = strlen(uri);
  snprintf(uri + len, size - len, "?model=%s", model);
}

// An open request for the printer at address; model may be NULL or empty
// when unknown, and the bridge then reads it from the advertised name.
static cJSON *
open_request(const char *address, const char *model)
{
  cJSON *request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "open");
  cJSON_AddStringToObject(request, "address", address);
  if (model && *model)
    cJSON_AddStringToObject(request, "model", model);
  return request;
}

// Connects a fresh bridge handle to the bridge's socket.
static bool
bridge_connect(phomemo_bridge_t *bridge, char *err, size_t errsize)
{
  char path[256];
  return phomemo_bridge_connect(bridge, phomemo_socket_path(path, sizeof(path)),
                                err, errsize);
}

static bool
phomemo_list_cb(pappl_device_cb_t cb, void *data, pappl_deverror_cb_t err_cb,
                void *err_data)
{
  phomemo_bridge_t bridge;
  char err[256];
  bool stopped = false;

  if (!bridge_connect(&bridge, err, sizeof(err)))
  {
    if (err_cb)
      err_cb(err, err_data);
    return false;
  }

  cJSON *request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "discover");
  cJSON_AddNumberToObject(request, "timeout", 5);
  cJSON *reply = phomemo_bridge_call(&bridge, request, NULL, 0, NULL, NULL,
                                     err, sizeof(err));
  cJSON_Delete(request);
  phomemo_bridge_close(&bridge);

  if (!reply)
  {
    if (err_cb)
      err_cb(err, err_data);
    return false;
  }

  cJSON *printers = cJSON_GetObjectItem(reply, "printers");
  cJSON *printer;
  cJSON_ArrayForEach(printer, printers)
  {
    cJSON *address = cJSON_GetObjectItem(printer, "address");
    cJSON *model_id = cJSON_GetObjectItem(printer, "model");
    const phomemo_model_t *model =
      cJSON_IsString(model_id) ? phomemo_model_find(model_id->valuestring)
                               : NULL;
    if (!cJSON_IsString(address) || !model)
      continue;

    char info[192];
    char uri[160];
    phomemo_device_info(model, address->valuestring, info, sizeof(info));
    format_uri(address->valuestring, model->id, uri, sizeof(uri));
    if (cb(info, uri, model->device_id, data))
    {
      stopped = true;
      break;
    }
  }

  cJSON_Delete(reply);
  return stopped;
}

// Connects to the bridge and opens the printer. Closes the handle again
// when the bridge rejects open.
static bool
open_bridge(phomemo_device_t *dev, char *err, size_t errsize)
{
  if (!bridge_connect(&dev->bridge, err, errsize))
    return false;

  cJSON *request = open_request(dev->address, dev->model);
  cJSON *reply = phomemo_bridge_call(&dev->bridge, request, NULL, 0, NULL, NULL,
                                     err, errsize);
  cJSON_Delete(request);
  if (!reply)
  {
    phomemo_bridge_close(&dev->bridge);
    return false;
  }
  cJSON_Delete(reply);
  return true;
}

static bool
phomemo_open_cb(pappl_device_t *device, const char *device_uri,
                const char *name)
{
  char err[256];

  phomemo_device_t *dev = calloc(1, sizeof(*dev));
  if (!dev)
    return false;
  dev->bridge.fd = -1;

  if (!parse_address(device_uri, dev->address, sizeof(dev->address)))
  {
    papplDeviceError(device, "Bad device URI '%s'.", device_uri);
    free(dev);
    return false;
  }
  phomemo_uri_model(device_uri, dev->model, sizeof(dev->model));

  if (!open_bridge(dev, err, sizeof(err)))
  {
    papplDeviceError(device, "Unable to reach phomemo-bridge: %s", err);
    free(dev);
    return false;
  }

  papplDeviceSetData(device, dev);
  return true;
}

phomemo_bridge_t *
phomemo_device_bridge(pappl_device_t *device, char *err, size_t errsize)
{
  phomemo_device_t *dev = papplDeviceGetData(device);

  if (!dev)
  {
    snprintf(err, errsize, "printer device is not open");
    return NULL;
  }
  if (dev->bridge.fd < 0 && !open_bridge(dev, err, errsize))
    return NULL;
  return &dev->bridge;
}

static void
phomemo_close_cb(pappl_device_t *device)
{
  phomemo_device_t *dev = papplDeviceGetData(device);
  if (!dev)
    return;

  if (dev->bridge.fd >= 0)
  {
    cJSON *request = cJSON_CreateObject();
    cJSON_AddStringToObject(request, "cmd", "close");
    cJSON_Delete(phomemo_bridge_call(&dev->bridge, request, NULL, 0, NULL,
                                     NULL, NULL, 0));
    cJSON_Delete(request);
  }
  phomemo_bridge_close(&dev->bridge);
  free(dev);
  papplDeviceSetData(device, NULL);
}

static ssize_t
phomemo_read_cb(pappl_device_t *device, void *buffer, size_t bytes)
{
  phomemo_device_t *dev = papplDeviceGetData(device);
  return dev && dev->bridge.fd >= 0 ? read(dev->bridge.fd, buffer, bytes) : -1;
}

static ssize_t
phomemo_write_cb(pappl_device_t *device, const void *buffer, size_t bytes)
{
  phomemo_device_t *dev = papplDeviceGetData(device);
  return dev && dev->bridge.fd >= 0 ? write(dev->bridge.fd, buffer, bytes) : -1;
}

// Sends status on a bridge connection and maps the reply onto printer
// state reasons; battery gets the charge in percent, or -1 when unknown.
// Returns false when the bridge did not answer.
// Not registered as the scheme's device status callback: a call while a
// job holds the connection would be taken for the job's pending reply.
static bool
query_status(phomemo_bridge_t *bridge, const char *address,
             pappl_preason_t *reasons, int *battery, char *err, size_t errsize)
{
  cJSON *request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "status");
  if (address)
    cJSON_AddStringToObject(request, "address", address);
  cJSON *reply = phomemo_bridge_call(bridge, request, NULL, 0, NULL, NULL, err,
                                     errsize);
  cJSON_Delete(request);
  if (!reply)
    return false;

  cJSON *lid = cJSON_GetObjectItem(reply, "lid");
  cJSON *paper = cJSON_GetObjectItem(reply, "paper");
  cJSON *charge = cJSON_GetObjectItem(reply, "battery");
  if (!charge)
  {
    // Without a connection the bridge reports what it last read from this printer.
    cJSON *seen = cJSON_GetObjectItem(reply, "last_seen");
    charge = cJSON_IsObject(seen) ? cJSON_GetObjectItem(seen, "battery") : NULL;
  }

  *battery = cJSON_IsNumber(charge) ? charge->valueint : -1;
  *reasons = PAPPL_PREASON_NONE;
  if (!cJSON_IsTrue(cJSON_GetObjectItem(reply, "connected")))
    *reasons = PAPPL_PREASON_OTHER;
  else if (cJSON_IsString(lid) && !strcmp(lid->valuestring, "open"))
    *reasons = PAPPL_PREASON_COVER_OPEN;
  else if (cJSON_IsString(paper) && !strcmp(paper->valuestring, "absent"))
    *reasons = PAPPL_PREASON_MEDIA_EMPTY;

  cJSON_Delete(reply);
  return true;
}

// Idle poll, called by PAPPL while no job holds the device. Uses a
// connection of its own; a missing or busy bridge leaves the reasons
// untouched, and a dropped printer connection clears them.
bool
phomemo_status_cb(pappl_printer_t *printer)
{
  phomemo_bridge_t bridge;
  pappl_preason_t reasons;
  int battery;
  char err[256];
  char address[32];

  if (!parse_address(papplPrinterGetDeviceURI(printer), address,
                     sizeof(address)) ||
      !bridge_connect(&bridge, err, sizeof(err)))
    return true;

  bool answered = query_status(&bridge, address, &reasons, &battery, err,
                               sizeof(err));
  phomemo_bridge_close(&bridge);
  if (!answered)
    return true;

  pappl_preason_t sensed = PAPPL_PREASON_COVER_OPEN | PAPPL_PREASON_MEDIA_EMPTY;
  papplPrinterSetReasons(printer, reasons & sensed, sensed & ~reasons);
  if (battery >= 0)
    phomemo_set_battery(printer, battery);
  return true;
}

void
phomemo_set_battery(pappl_printer_t *printer, int percent)
{
  pappl_supply_t supply;

  memset(&supply, 0, sizeof(supply));
  supply.color = PAPPL_SUPPLY_COLOR_NO_COLOR;
  snprintf(supply.description, sizeof(supply.description), "Battery");
  supply.is_consumed = true;
  supply.level = percent;
  // IPP has no battery supply type, and GNOME Settings shows levels only for
  // ink and toner supplies, so the battery is reported as ink.
  supply.type = PAPPL_SUPPLY_TYPE_INK;
  papplPrinterSetSupplies(printer, 1, &supply);
}

void
phomemo_identify_cb(pappl_printer_t *printer, pappl_identify_actions_t actions,
                    const char *message)
{
  phomemo_bridge_t bridge;
  char address[64];
  char err[256];

  if (!parse_address(papplPrinterGetDeviceURI(printer), address,
                     sizeof(address)) ||
      !bridge_connect(&bridge, err, sizeof(err)))
  {
    papplLogPrinter(printer, PAPPL_LOGLEVEL_WARN,
                    "Identify: phomemo-bridge not reachable.");
    return;
  }

  cJSON *request =
    open_request(address, papplPrinterGetDriverName(printer));
  cJSON *reply = phomemo_bridge_call(&bridge, request, NULL, 0, NULL, NULL,
                                     err, sizeof(err));
  cJSON_Delete(request);
  if (reply)
  {
    cJSON_Delete(reply);
    request = cJSON_CreateObject();
    cJSON_AddStringToObject(request, "cmd", "identify");
    reply = phomemo_bridge_call(&bridge, request, NULL, 0, NULL, NULL, err,
                                sizeof(err));
    cJSON_Delete(request);
  }
  if (!reply)
    papplLogPrinter(printer, PAPPL_LOGLEVEL_WARN, "Identify failed: %s", err);
  cJSON_Delete(reply);

  request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "close");
  cJSON_Delete(phomemo_bridge_call(&bridge, request, NULL, 0, NULL, NULL,
                                   NULL, 0));
  cJSON_Delete(request);
  phomemo_bridge_close(&bridge);
}

static char *
phomemo_id_cb(pappl_device_t *device, char *buffer, size_t bufsize)
{
  phomemo_device_t *dev = papplDeviceGetData(device);
  const phomemo_model_t *model = dev ? phomemo_model_find(dev->model) : NULL;
  snprintf(buffer, bufsize, "%s",
           model ? model->device_id : "MFG:Phomemo;CMD:PHOMEMO;");
  return buffer;
}

const char *
phomemo_testpage_cb(pappl_printer_t *printer, char *buffer, size_t bufsize)
{
  phomemo_bridge_t bridge;
  char address[64];
  char err[256];
  const char *result = NULL;

  if (!parse_address(papplPrinterGetDeviceURI(printer), address,
                     sizeof(address)) ||
      !bridge_connect(&bridge, err, sizeof(err)))
  {
    papplLogPrinter(printer, PAPPL_LOGLEVEL_WARN,
                    "Test page: phomemo-bridge not reachable.");
    return NULL;
  }

  cJSON *request =
    open_request(address, papplPrinterGetDriverName(printer));
  cJSON *reply = phomemo_bridge_call(&bridge, request, NULL, 0, NULL, NULL,
                                     err, sizeof(err));
  cJSON_Delete(request);
  if (reply)
  {
    cJSON_Delete(reply);
    request = cJSON_CreateObject();
    cJSON_AddStringToObject(request, "cmd", "test_page");
    cJSON_AddStringToObject(request, "printer_name",
                            papplPrinterGetName(printer));
    cJSON *versions = cJSON_AddObjectToObject(request, "versions");
    cJSON_AddStringToObject(versions, "phomemo-printer-app", PHOMEMO_VERSION);
    cJSON_AddStringToObject(versions, "pappl", PAPPL_VERSION_STR);
    reply = phomemo_bridge_call(&bridge, request, NULL, 0, NULL, NULL, err,
                                sizeof(err));
    cJSON_Delete(request);
  }
  if (reply)
  {
    cJSON *path = cJSON_GetObjectItem(reply, "path");
    if (cJSON_IsString(path))
    {
      snprintf(buffer, bufsize, "%s", path->valuestring);
      result = buffer;
    }
    cJSON_Delete(reply);
  }
  if (!result)
    papplLogPrinter(printer, PAPPL_LOGLEVEL_WARN, "Test page failed: %s", err);

  request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "close");
  cJSON_Delete(phomemo_bridge_call(&bridge, request, NULL, 0, NULL, NULL,
                                   NULL, 0));
  cJSON_Delete(request);
  phomemo_bridge_close(&bridge);
  return result;
}

void
phomemo_device_add_scheme(void)
{
  papplDeviceAddScheme(PHOMEMO_URI_SCHEME, PAPPL_DEVTYPE_CUSTOM_LOCAL,
                       phomemo_list_cb, phomemo_open_cb, phomemo_close_cb,
                       phomemo_read_cb, phomemo_write_cb, NULL,
                       phomemo_id_cb);
}
