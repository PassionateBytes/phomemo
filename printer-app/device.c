// The phomemo:// device scheme. A device is one bridge connection; the
// URI host part is the printer's BLE address.

#include "phomemo.h"
#include "bridge.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define URI_PREFIX PHOMEMO_URI_SCHEME "://"

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

// Builds the device URI for a BLE address (colons become dashes).
static void
format_uri(const char *address, char *uri, size_t size)
{
  size_t prefix = strlen(URI_PREFIX);
  snprintf(uri, size, "%s%s", URI_PREFIX, address);
  for (char *p = uri + prefix; *p; p++)
    if (*p == ':')
      *p = '-';
}

// Connects a fresh bridge handle to the daemon's socket.
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

  cJSON *printer;
  cJSON_ArrayForEach(printer, cJSON_GetObjectItem(reply, "printers"))
  {
    cJSON *address = cJSON_GetObjectItem(printer, "address");
    if (!cJSON_IsString(address))
      continue;

    char uri[128];
    format_uri(address->valuestring, uri, sizeof(uri));
    if (cb(PHOMEMO_MAKE_AND_MODEL, uri, PHOMEMO_DEVICE_ID, data))
    {
      stopped = true;
      break;
    }
  }

  cJSON_Delete(reply);
  return stopped;
}

static bool
phomemo_open_cb(pappl_device_t *device, const char *device_uri,
                const char *name)
{
  char address[64];
  char err[256];

  if (!parse_address(device_uri, address, sizeof(address)))
  {
    papplDeviceError(device, "Bad device URI '%s'.", device_uri);
    return false;
  }

  phomemo_bridge_t *bridge = calloc(1, sizeof(*bridge));
  if (!bridge)
    return false;

  if (!bridge_connect(bridge, err, sizeof(err)))
  {
    papplDeviceError(device, "Unable to reach phomemo-bridge: %s", err);
    free(bridge);
    return false;
  }

  cJSON *request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "open");
  cJSON_AddStringToObject(request, "address", address);
  cJSON *reply = phomemo_bridge_call(bridge, request, NULL, 0, NULL, NULL, err,
                                     sizeof(err));
  cJSON_Delete(request);
  if (!reply)
  {
    papplDeviceError(device, "phomemo-bridge rejected open: %s", err);
    phomemo_bridge_close(bridge);
    free(bridge);
    return false;
  }
  cJSON_Delete(reply);

  papplDeviceSetData(device, bridge);
  return true;
}

static void
phomemo_close_cb(pappl_device_t *device)
{
  phomemo_bridge_t *bridge = papplDeviceGetData(device);
  if (!bridge)
    return;

  cJSON *request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "close");
  cJSON_Delete(phomemo_bridge_call(bridge, request, NULL, 0, NULL, NULL, NULL,
                                   0));
  cJSON_Delete(request);
  phomemo_bridge_close(bridge);
  free(bridge);
  papplDeviceSetData(device, NULL);
}

static ssize_t
phomemo_read_cb(pappl_device_t *device, void *buffer, size_t bytes)
{
  phomemo_bridge_t *bridge = papplDeviceGetData(device);
  return bridge ? read(bridge->fd, buffer, bytes) : -1;
}

static ssize_t
phomemo_write_cb(pappl_device_t *device, const void *buffer, size_t bytes)
{
  phomemo_bridge_t *bridge = papplDeviceGetData(device);
  return bridge ? write(bridge->fd, buffer, bytes) : -1;
}

// Sends status on a bridge connection and maps the reply onto printer
// state reasons. Returns false when the bridge did not answer.
static bool
query_status(phomemo_bridge_t *bridge, pappl_preason_t *reasons, char *err,
             size_t errsize)
{
  cJSON *request = cJSON_CreateObject();
  cJSON_AddStringToObject(request, "cmd", "status");
  cJSON *reply = phomemo_bridge_call(bridge, request, NULL, 0, NULL, NULL, err,
                                     errsize);
  cJSON_Delete(request);
  if (!reply)
    return false;

  cJSON *lid = cJSON_GetObjectItem(reply, "lid");
  cJSON *paper = cJSON_GetObjectItem(reply, "paper");

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

static pappl_preason_t
phomemo_devstatus_cb(pappl_device_t *device)
{
  phomemo_bridge_t *bridge = papplDeviceGetData(device);
  pappl_preason_t reasons;
  char err[256];

  if (!bridge)
    return PAPPL_PREASON_OTHER;

  if (!query_status(bridge, &reasons, err, sizeof(err)))
  {
    papplDeviceError(device, "phomemo-bridge status failed: %s", err);
    return PAPPL_PREASON_OTHER;
  }
  return reasons;
}

// Idle poll, called by PAPPL while no job holds the device. Uses a
// connection of its own; a missing or busy bridge leaves the reasons
// untouched, and a released printer link clears them.
bool
phomemo_status_cb(pappl_printer_t *printer)
{
  phomemo_bridge_t bridge;
  pappl_preason_t reasons;
  char err[256];

  if (!bridge_connect(&bridge, err, sizeof(err)))
    return true;

  bool answered = query_status(&bridge, &reasons, err, sizeof(err));
  phomemo_bridge_close(&bridge);
  if (!answered)
    return true;

  pappl_preason_t sensed = PAPPL_PREASON_COVER_OPEN | PAPPL_PREASON_MEDIA_EMPTY;
  papplPrinterSetReasons(printer, reasons & sensed, sensed & ~reasons);
  return true;
}

static char *
phomemo_id_cb(pappl_device_t *device, char *buffer, size_t bufsize)
{
  snprintf(buffer, bufsize, "%s", PHOMEMO_DEVICE_ID);
  return buffer;
}

void
phomemo_device_add_scheme(void)
{
  papplDeviceAddScheme(PHOMEMO_URI_SCHEME, PAPPL_DEVTYPE_CUSTOM_LOCAL,
                       phomemo_list_cb, phomemo_open_cb, phomemo_close_cb,
                       phomemo_read_cb, phomemo_write_cb, phomemo_devstatus_cb,
                       phomemo_id_cb);
}
