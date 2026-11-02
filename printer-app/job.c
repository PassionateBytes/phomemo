// Raster job pipeline: streams PAPPL's raster lines to the bridge as pages.

#include "phomemo.h"

bool
phomemo_rstartjob_cb(pappl_job_t *job, pappl_pr_options_t *options,
                     pappl_device_t *device)
{
  return true;
}

bool
phomemo_rstartpage_cb(pappl_job_t *job, pappl_pr_options_t *options,
                      pappl_device_t *device, unsigned page)
{
  return true;
}

bool
phomemo_rwriteline_cb(pappl_job_t *job, pappl_pr_options_t *options,
                      pappl_device_t *device, unsigned y,
                      const unsigned char *line)
{
  return true;
}

bool
phomemo_rendpage_cb(pappl_job_t *job, pappl_pr_options_t *options,
                    pappl_device_t *device, unsigned page)
{
  return true;
}

bool
phomemo_rendjob_cb(pappl_job_t *job, pappl_pr_options_t *options,
                   pappl_device_t *device)
{
  return true;
}

bool
phomemo_status_cb(pappl_printer_t *printer)
{
  return true;
}
