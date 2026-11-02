// Entry point: registers the m08f driver and hands control to PAPPL's main
// loop (server, add, devices, drivers and the other standard subcommands).

#include "phomemo.h"

#include <string.h>

static pappl_pr_driver_t drivers[] = {
  {PHOMEMO_DRIVER_NAME, PHOMEMO_MAKE_AND_MODEL, PHOMEMO_DEVICE_ID, NULL},
};

static const char *footer_html =
  "Phomemo printer application. Printing goes through phomemo-bridge.";

const char *
phomemo_autoadd_cb(const char *device_info, const char *device_uri,
                   const char *device_id, void *data)
{
  if (device_uri && !strncmp(device_uri, PHOMEMO_URI_SCHEME "://",
                             sizeof(PHOMEMO_URI_SCHEME) + 2))
    return PHOMEMO_DRIVER_NAME;
  return NULL;
}

int
main(int argc, char *argv[])
{
  phomemo_device_add_scheme();
  return papplMainloop(argc, argv, PHOMEMO_VERSION, footer_html,
                       (int)(sizeof(drivers) / sizeof(drivers[0])), drivers,
                       phomemo_autoadd_cb, phomemo_driver_cb, NULL, NULL,
                       NULL, NULL, NULL);
}
