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

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

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

static char self_path[1024];

// The server's control socket, as PAPPL derives it: under $SNAP_COMMON
// for root inside a snap, in /run for root otherwise, in the temporary
// directory with the user ID for everyone else.
static void
server_socket_path(char *buffer, size_t bufsize)
{
  const char *snap_common = getenv("SNAP_COMMON");
  const char *tmpdir = getenv("TMPDIR");

  if (getuid() == 0 && snap_common && *snap_common)
  {
    snprintf(buffer, bufsize, "%s/phomemo-printer-app.sock", snap_common);
    return;
  }
  if (getuid() == 0)
  {
    snprintf(buffer, bufsize, "/run/phomemo-printer-app.sock");
    return;
  }
  if (!tmpdir || !*tmpdir || access(tmpdir, W_OK))
    tmpdir = "/tmp";
  snprintf(buffer, bufsize, "%s/phomemo-printer-app%d.sock", tmpdir,
           (int)getuid());
}

// Runs autoadd once the server listens: printers in range get registered
// at every start, not only at the first one.
static void *
register_at_start(void *data)
{
  char socket_path[1200];
  char command[1200];
  struct stat info;

  server_socket_path(socket_path, sizeof(socket_path));
  for (int i = 0; i < 60 && stat(socket_path, &info) != 0; i++)
    sleep(1);
  if (stat(socket_path, &info) != 0)
  {
    fprintf(stderr,
            "phomemo-printer-app: server socket %s did not appear; "
            "no printer registration at start.\n",
            socket_path);
    return NULL;
  }
  sleep(1);
  fprintf(stderr, "phomemo-printer-app: registering printers in range.\n");
  snprintf(command, sizeof(command), "'%s' autoadd", self_path);
  if (system(command) != 0)
    fprintf(stderr, "phomemo-printer-app: autoadd at start failed.\n");
  return NULL;
}

int
main(int argc, char *argv[])
{
  ssize_t len = readlink("/proc/self/exe", self_path, sizeof(self_path) - 1);
  if (len > 0)
    self_path[len] = '\0';
  else
    snprintf(self_path, sizeof(self_path), "%s", argv[0]);

  // PAPPL reads "-h HOST"; a lone "-h" means help.
  if (argc == 2 && !strcmp(argv[1], "-h"))
    argv[1] = (char *)"--help";

  phomemo_device_add_scheme();

  if (argc >= 2 && !strcmp(argv[1], "server"))
  {
    pthread_t thread;
    if (pthread_create(&thread, NULL, register_at_start, NULL) == 0)
      pthread_detach(thread);
  }

  return papplMainloop(argc, argv, PHOMEMO_VERSION, footer_html,
                       (int)(sizeof(drivers) / sizeof(drivers[0])), drivers,
                       phomemo_autoadd_cb, phomemo_driver_cb, NULL, NULL,
                       NULL, NULL, NULL);
}
