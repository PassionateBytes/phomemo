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
#define PHOMEMO_DPI 203
#define PHOMEMO_HEAD_WIDTH 21000  // print head width in hundredths of a millimetre
// Top and bottom margin in hundredths of a millimetre. PAPPL only models
// symmetric margins, so the 10 mm the printer cannot reach at the top of
// a sheet applies to both ends; the bridge clips the last 6 mm regardless.
#define PHOMEMO_MARGIN 1000
#define PHOMEMO_TONE_OPTION "phomemo-tone"

// Registers the phomemo:// device scheme with PAPPL. The URI host part
// is the printer's BLE address with dashes instead of colons
// (phomemo://60-6E-41-23-0B-D6), because a URI host cannot hold colons.
void phomemo_device_add_scheme(void);

// Resolves the bridge socket path: $PHOMEMO_BRIDGE_SOCKET, else
// $XDG_RUNTIME_DIR/phomemo-bridge.sock, else /run/phomemo/bridge.sock.
const char *phomemo_socket_path(char *buffer, size_t bufsize);

// Driver callback registered with PAPPL for the "m08f" driver.
bool phomemo_driver_cb(pappl_system_t *system, const char *driver_name,
                       const char *device_uri, const char *device_id,
                       pappl_pr_driver_data_t *data, ipp_t **attrs,
                       void *cbdata);

// Printer density keyword for an IPP print-quality value.
const char *phomemo_density_for_quality(ipp_quality_t quality);

// Bridge content keyword for a print-content-optimize value.
const char *phomemo_content_name(pappl_content_t content);

// True when the page must be rotated to feed A5 long edge first.
bool phomemo_should_rotate(const pappl_pr_options_t *options);

// Media length along the feed direction in millimetres (A5 feeds its
// 210 mm edge across the head, so its feed length is 148 mm).
double phomemo_media_length_mm(const pappl_pr_options_t *options);

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

// Printer status callback: refreshes printer-state-reasons.
bool phomemo_status_cb(pappl_printer_t *printer);

// Picks the driver for a discovered device URI.
const char *phomemo_autoadd_cb(const char *device_info, const char *device_uri,
                               const char *device_id, void *data);

#endif // PHOMEMO_H
