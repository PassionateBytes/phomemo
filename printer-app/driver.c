// The m08f driver: printer capabilities and the mapping of IPP job
// options onto bridge parameters.

#include "phomemo.h"

#include <string.h>

static const char *const tone_keywords[] = {"auto", "threshold", "ordered",
                                            "diffusion"};

static const char *const media_sizes[] = {"iso_a4_210x297mm",
                                          "iso_a5_148x210mm"};

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

bool
phomemo_should_rotate(const pappl_pr_options_t *options)
{
  return !strncmp(options->media.size_name, "iso_a5", 6) &&
         options->header.cupsHeight > options->header.cupsWidth;
}

double
phomemo_media_length_mm(const pappl_pr_options_t *options)
{
  return options->media.size_length / 100.0;
}

// Fills a media-col for a supported size with the printer's margins.
static void
set_media(pappl_media_col_t *media, const char *size_name, int width,
          int length)
{
  memset(media, 0, sizeof(*media));
  snprintf(media->size_name, sizeof(media->size_name), "%s", size_name);
  media->size_width = width;
  media->size_length = length;
  media->top_margin = PHOMEMO_MARGIN;
  media->bottom_margin = PHOMEMO_MARGIN;
  media->left_margin = 0;
  media->right_margin = 0;
  snprintf(media->source, sizeof(media->source), "main");
  snprintf(media->type, sizeof(media->type), "stationery");
}

bool
phomemo_driver_cb(pappl_system_t *system, const char *driver_name,
                  const char *device_uri, const char *device_id,
                  pappl_pr_driver_data_t *data, ipp_t **attrs, void *cbdata)
{
  if (strcmp(driver_name, PHOMEMO_DRIVER_NAME))
    return false;

  data->rstartjob_cb = phomemo_rstartjob_cb;
  data->rstartpage_cb = phomemo_rstartpage_cb;
  data->rwriteline_cb = phomemo_rwriteline_cb;
  data->rendpage_cb = phomemo_rendpage_cb;
  data->rendjob_cb = phomemo_rendjob_cb;
  data->status_cb = phomemo_status_cb;

  snprintf(data->make_and_model, sizeof(data->make_and_model), "%s",
           PHOMEMO_MAKE_AND_MODEL);
  data->kind = PAPPL_KIND_DOCUMENT;
  data->ppm = 1;
  data->raster_types =
    PAPPL_PWG_RASTER_TYPE_SGRAY_8 | PAPPL_PWG_RASTER_TYPE_BLACK_1;
  data->num_resolution = 1;
  data->x_resolution[0] = PHOMEMO_DPI;
  data->y_resolution[0] = PHOMEMO_DPI;
  data->x_default = PHOMEMO_DPI;
  data->y_default = PHOMEMO_DPI;
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
  data->type[0] = "stationery";
  data->num_media = (int)(sizeof(media_sizes) / sizeof(media_sizes[0]));
  for (int i = 0; i < data->num_media; i++)
    data->media[i] = media_sizes[i];

  data->left_right = 0;
  data->bottom_top = PHOMEMO_MARGIN;
  set_media(&data->media_default, "iso_a4_210x297mm", 21000, 29700);
  data->media_ready[0] = data->media_default;

  data->num_vendor = 1;
  data->vendor[0] = PHOMEMO_TONE_OPTION;

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
