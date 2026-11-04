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

// Entry point: registers the m08f driver and hands control to PAPPL's main
// loop (server, add, autoadd, devices, printers and the other standard
// subcommands). The server registers printers in range once at every
// start; PAPPL alone does that only at the very first start.

#include "phomemo.h"

#include <stdio.h>
#include <string.h>

static const char *footer_html =
  "Phomemo printer application. Printing goes through phomemo-bridge.";

const char *
phomemo_autoadd_cb(const char *device_info, const char *device_uri,
                   const char *device_id, void *data)
{
  if (!device_uri || strncmp(device_uri, PHOMEMO_URI_SCHEME "://",
                             sizeof(PHOMEMO_URI_SCHEME) + 2))
    return NULL;
  const phomemo_model_t *model = phomemo_model_for_device_id(device_id);
  return model ? model->id : NULL;
}

int
main(int argc, char *argv[])
{
  static pappl_pr_driver_t drivers[PHOMEMO_MAX_MODELS];
  char err[1024];
  bool info_only = argc == 2 && (!strcmp(argv[1], "--help") ||
                                 !strcmp(argv[1], "--version"));

  int num_drivers = phomemo_models_load(NULL, err, sizeof(err));
  if (!num_drivers && !info_only)
  {
    fprintf(stderr, "phomemo-printer-app: %s\n", err);
    return 1;
  }
  for (int i = 0; i < num_drivers; i++)
  {
    const phomemo_model_t *model = phomemo_model_at(i);
    drivers[i].name = model->id;
    drivers[i].description = model->make_and_model;
    drivers[i].device_id = model->device_id;
    drivers[i].extension = NULL;
  }

  phomemo_device_add_scheme();

  return papplMainloop(argc, argv, PHOMEMO_VERSION, footer_html, num_drivers,
                       drivers, phomemo_autoadd_cb, phomemo_driver_cb, NULL,
                       NULL, NULL, NULL, NULL);
}
