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

#define PHOMEMO_VERSION "0.1.0"
#define PHOMEMO_DRIVER_NAME "m08f"
#define PHOMEMO_MAKE_AND_MODEL "Phomemo M08F"
#define PHOMEMO_DEVICE_ID "MFG:Phomemo;MDL:M08F;CMD:PHOMEMO;"
#define PHOMEMO_URI_SCHEME "phomemo"

// Registers the phomemo:// device scheme with PAPPL.
void phomemo_device_add_scheme(void);

// Resolves the bridge socket path: $PHOMEMO_BRIDGE_SOCKET, else
// $XDG_RUNTIME_DIR/phomemo-bridge.sock, else /run/phomemo/bridge.sock.
const char *phomemo_socket_path(char *buffer, size_t bufsize);

// Driver callback registered with PAPPL for the "m08f" driver.
bool phomemo_driver_cb(pappl_system_t *system, const char *driver_name,
                       const char *device_uri, const char *device_id,
                       pappl_pr_driver_data_t *data, ipp_t **attrs,
                       void *cbdata);

// Picks the driver for a discovered device URI.
const char *phomemo_autoadd_cb(const char *device_info, const char *device_uri,
                               const char *device_id, void *data);

#endif // PHOMEMO_H
