// Entry point: registers the m08f driver and hands control to PAPPL's main
// loop (server, add, autoadd, devices, printers and the other standard
// subcommands). The server also registers the first printer it can find
// during its first hour, after that registration is manual.

#include "phomemo.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static pappl_pr_driver_t drivers[] = {
  {PHOMEMO_DRIVER_NAME, PHOMEMO_MAKE_AND_MODEL, PHOMEMO_DEVICE_ID, NULL},
};

static const char *footer_html =
  "Phomemo printer application. Printing goes through phomemo-bridge.";

static char self_path[1024];

const char *
phomemo_autoadd_cb(const char *device_info, const char *device_uri,
                   const char *device_id, void *data)
{
  if (device_uri && !strncmp(device_uri, PHOMEMO_URI_SCHEME "://",
                             sizeof(PHOMEMO_URI_SCHEME) + 2))
    return PHOMEMO_DRIVER_NAME;
  return NULL;
}

// Seconds from an environment variable, or the default.
static long
env_seconds(const char *name, long fallback)
{
  const char *value = getenv(name);
  return value && *value ? atol(value) : fallback;
}

// The file whose mtime marks the server's first start.
static void
marker_path(char *buffer, size_t bufsize)
{
  const char *config = getenv("XDG_CONFIG_HOME");
  const char *home = getenv("HOME");

  if (config && *config)
    snprintf(buffer, bufsize, "%s/phomemo-printer-app.first-start", config);
  else
    snprintf(buffer, bufsize, "%s/.config/phomemo-printer-app.first-start",
             home ? home : "");
}

// Runs one of our own subcommands against the running server; returns
// true when it printed anything.
static bool
subcommand_has_output(const char *subcommand)
{
  char command[1200];
  char line[256];
  bool output = false;

  snprintf(command, sizeof(command), "'%s' %s 2>/dev/null", self_path,
           subcommand);
  FILE *fp = popen(command, "r");
  if (!fp)
    return false;
  while (fgets(line, sizeof(line), fp))
    output = true;
  pclose(fp);
  return output;
}

// Scans for a printer through the bridge at intervals during the server's
// first hour, until one is configured.
static void *
auto_register(void *data)
{
  char marker[1200];
  char command[1200];
  struct stat info;
  time_t started;
  long window = env_seconds("PHOMEMO_AUTOADD_WINDOW", 3600);
  long interval = env_seconds("PHOMEMO_AUTOADD_INTERVAL", 30);

  marker_path(marker, sizeof(marker));
  if (stat(marker, &info) == 0)
  {
    started = info.st_mtime;
  }
  else
  {
    FILE *fp = fopen(marker, "w");
    if (fp)
      fclose(fp);
    started = time(NULL);
  }
  if (time(NULL) - started >= window)
    return NULL;

  fprintf(stderr,
          "phomemo-printer-app: looking for a printer every %ld s during the "
          "first %ld s after the first start.\n",
          interval, window);
  snprintf(command, sizeof(command), "'%s' autoadd >/dev/null 2>&1",
           self_path);
  sleep((unsigned)(interval < 5 ? interval : 5));
  while (time(NULL) - started < window)
  {
    if (subcommand_has_output("printers"))
    {
      fprintf(stderr, "phomemo-printer-app: a printer is configured; "
                      "automatic registration done.\n");
      return NULL;
    }
    if (system(command) != 0)
      fprintf(stderr, "phomemo-printer-app: autoadd failed.\n");
    sleep((unsigned)interval);
  }
  fprintf(stderr, "phomemo-printer-app: first hour over, no printer found; "
                  "register one with autoadd or the web interface.\n");
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
    if (pthread_create(&thread, NULL, auto_register, NULL) == 0)
      pthread_detach(thread);
  }

  return papplMainloop(argc, argv, PHOMEMO_VERSION, footer_html,
                       (int)(sizeof(drivers) / sizeof(drivers[0])), drivers,
                       phomemo_autoadd_cb, phomemo_driver_cb, NULL, NULL,
                       NULL, NULL, NULL);
}
