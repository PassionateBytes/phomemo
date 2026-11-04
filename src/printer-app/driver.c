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

// The m08f driver: printer capabilities and the mapping of IPP job
// options onto bridge parameters.

#include "phomemo.h"

#include <pthread.h>
#include <stdlib.h>
#include <string.h>

static const char *const tone_keywords[] = {"auto", "threshold", "ordered",
                                            "diffusion"};

const char *
phomemo_density_for_quality(ipp_quality_t quality)
{
  switch (quality)
  {
  case IPP_QUALITY_DRAFT:
    return "low";
  case IPP_QUALITY_HIGH:
    return "high";
  default:
    return "medium";
  }
}

const char *
phomemo_content_name(pappl_content_t content)
{
  switch (content)
  {
  case PAPPL_CONTENT_TEXT:
    return "text";
  case PAPPL_CONTENT_GRAPHIC:
  case PAPPL_CONTENT_TEXT_AND_GRAPHIC:
    return "graphic";
  case PAPPL_CONTENT_PHOTO:
    return "photo";
  default:
    return "auto";
  }
}

// The dimension closest to the head width lies across the head; the other
// one runs along the feed.
static bool
width_across(const pappl_pr_options_t *options, int head_width)
{
  return abs(options->media.size_width - head_width) <=
         abs(options->media.size_length - head_width);
}

bool
phomemo_should_rotate(const pappl_pr_options_t *options, int head_width)
{
  return !width_across(options, head_width) &&
         options->header.cupsHeight > options->header.cupsWidth;
}

double
phomemo_media_length_mm(const pappl_pr_options_t *options, int head_width)
{
  return (width_across(options, head_width) ? options->media.size_length
                                            : options->media.size_width) /
         100.0;
}

// PAPPL only models symmetric margins, so the larger of the model's top and
// bottom margin applies to both ends; the bridge lays pages out with the
// real ones.
static int
symmetric_margin(const phomemo_model_t *model)
{
  return model->top_margin > model->bottom_margin ? model->top_margin
                                                  : model->bottom_margin;
}

// Fills a media-col for a supported size with the model's margins.
static void
set_media(pappl_media_col_t *media, const phomemo_model_t *model,
          const char *size_name)
{
  pwg_media_t *pwg = pwgMediaForPWG(size_name);
  memset(media, 0, sizeof(*media));
  snprintf(media->size_name, sizeof(media->size_name), "%s", size_name);
  media->size_width = pwg ? pwg->width : 0;
  media->size_length = pwg ? pwg->length : 0;
  media->top_margin = symmetric_margin(model);
  media->bottom_margin = symmetric_margin(model);
  media->left_margin = 0;
  media->right_margin = 0;
  snprintf(media->source, sizeof(media->source), "main");
  snprintf(media->type, sizeof(media->type), PHOMEMO_MEDIA_TYPE);
}

// Human-readable labels for the vendor option in the web interface.
static const char *const strings_en =
  "\"" PHOMEMO_TONE_OPTION "\" = \"Rendering\";\n"
  "\"" PHOMEMO_TONE_OPTION ".auto\" = \"Automatic\";\n"
  "\"" PHOMEMO_TONE_OPTION ".threshold\" = \"Black and white\";\n"
  "\"" PHOMEMO_TONE_OPTION ".ordered\" = \"Ordered dither\";\n"
  "\"" PHOMEMO_TONE_OPTION ".diffusion\" = \"Diffusion dither\";\n"
  "\"media-type." PHOMEMO_MEDIA_TYPE "\" = \"Thermal paper\";\n";

// The option labels for the web interface. PAPPL's main loop has no hook
// between creating the system and loading printers, so the driver callback
// registers them with the first printer.
static void
publish_strings(pappl_system_t *system)
{
  static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
  static pappl_system_t *published = NULL;

  pthread_mutex_lock(&lock);
  if (published != system)
  {
    published = system;
    papplSystemAddStringsData(system, "/phomemo.strings", "en", strings_en);
  }
  pthread_mutex_unlock(&lock);
}

bool
phomemo_driver_cb(pappl_system_t *system, const char *driver_name,
                  const char *device_uri, const char *device_id,
                  pappl_pr_driver_data_t *data, ipp_t **attrs, void *cbdata)
{
  const phomemo_model_t *model = phomemo_model_find(driver_name);
  if (!model)
    return false;

  for (int i = 0; i < 3; i++)
    snprintf(data->icons[i].filename, sizeof(data->icons[i].filename), "%s",
             model->icons[i]);

  data->testpage_cb = phomemo_testpage_cb;
  data->identify_cb = phomemo_identify_cb;
  data->identify_supported = PAPPL_IDENTIFY_ACTIONS_SOUND;
  data->identify_default = PAPPL_IDENTIFY_ACTIONS_SOUND;
  data->has_supplies = true;
  data->rstartjob_cb = phomemo_rstartjob_cb;
  data->rstartpage_cb = phomemo_rstartpage_cb;
  data->rwriteline_cb = phomemo_rwriteline_cb;
  data->rendpage_cb = phomemo_rendpage_cb;
  data->rendjob_cb = phomemo_rendjob_cb;
  data->status_cb = phomemo_status_cb;

  snprintf(data->make_and_model, sizeof(data->make_and_model), "%s",
           model->make_and_model);
  data->kind = PAPPL_KIND_DOCUMENT;
  data->ppm = 1;
  // sgray_8 only: PAPPL hands a black_1 document to the driver as packed
  // bits under an 8-bit page header, so offering black_1 would print
  // garbage for clients that choose it. The bridge dithers 8-bit pages.
  data->raster_types = PAPPL_PWG_RASTER_TYPE_SGRAY_8;
  data->num_resolution = 1;
  data->x_resolution[0] = model->dpi;
  data->y_resolution[0] = model->dpi;
  data->x_default = model->dpi;
  data->y_default = model->dpi;
  data->color_supported = PAPPL_COLOR_MODE_MONOCHROME;
  data->color_default = PAPPL_COLOR_MODE_MONOCHROME;
  data->quality_default = IPP_QUALITY_NORMAL;
  data->content_default = PAPPL_CONTENT_AUTO;
  data->scaling_default = PAPPL_SCALING_FIT;
  data->duplex = PAPPL_DUPLEX_NONE;
  data->sides_supported = PAPPL_SIDES_ONE_SIDED;
  data->sides_default = PAPPL_SIDES_ONE_SIDED;

  data->num_source = 1;
  data->source[0] = "main";
  data->num_type = 1;
  data->type[0] = PHOMEMO_MEDIA_TYPE;
  data->num_media = model->num_media;
  for (int i = 0; i < data->num_media; i++)
    data->media[i] = model->media[i];

  data->left_right = 0;
  data->bottom_top = symmetric_margin(model);
  set_media(&data->media_default, model, model->media[model->default_media]);
  data->media_ready[0] = data->media_default;

  data->num_vendor = 1;
  data->vendor[0] = PHOMEMO_TONE_OPTION;

  publish_strings(system);

  if (!*attrs)
    *attrs = ippNew();
  ippAddStrings(*attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD,
                PHOMEMO_TONE_OPTION "-supported",
                (int)(sizeof(tone_keywords) / sizeof(tone_keywords[0])), NULL,
                tone_keywords);
  ippAddString(*attrs, IPP_TAG_PRINTER, IPP_TAG_KEYWORD,
               PHOMEMO_TONE_OPTION "-default", NULL, "auto");
  return true;
}
