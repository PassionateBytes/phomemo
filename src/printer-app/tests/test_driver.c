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

// Unit tests of the driver's option mapping helpers.

#include "phomemo.h"

#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

// Options for a media size (hundredths of a millimetre) and raster size.
static pappl_pr_options_t
options_for(const char *size_name, int size_width, int size_length,
            unsigned width, unsigned height)
{
  pappl_pr_options_t o;
  memset(&o, 0, sizeof(o));
  snprintf(o.media.size_name, sizeof(o.media.size_name), "%s", size_name);
  o.media.size_width = size_width;
  o.media.size_length = size_length;
  o.header.cupsWidth = width;
  o.header.cupsHeight = height;
  return o;
}

int
main(void)
{
  assert(!strcmp(phomemo_density_for_quality(IPP_QUALITY_DRAFT), "low"));
  assert(!strcmp(phomemo_density_for_quality(IPP_QUALITY_NORMAL), "medium"));
  assert(!strcmp(phomemo_density_for_quality(IPP_QUALITY_HIGH), "high"));
  assert(!strcmp(phomemo_density_for_quality((ipp_quality_t)0), "medium"));

  assert(!strcmp(phomemo_content_name(PAPPL_CONTENT_AUTO), "auto"));
  assert(!strcmp(phomemo_content_name(PAPPL_CONTENT_TEXT), "text"));
  assert(!strcmp(phomemo_content_name(PAPPL_CONTENT_GRAPHIC), "graphic"));
  assert(!strcmp(phomemo_content_name(PAPPL_CONTENT_TEXT_AND_GRAPHIC),
                 "graphic"));
  assert(!strcmp(phomemo_content_name(PAPPL_CONTENT_PHOTO), "photo"));

  char err[256] = "";
  unsetenv("PHOMEMO_MODELS_DIR");
  assert(phomemo_models_load(NULL, err, sizeof(err)) == 1);
  const phomemo_model_t *embedded = phomemo_model_find("m08f");
  assert(embedded);
  assert(!strcmp(embedded->make_and_model, "Phomemo M08F"));
  for (int i = 0; i < 3; i++)
    assert(embedded->icon_data[i] && embedded->icon_len[i] > 100 &&
           !embedded->icons[i][0]);

  assert(phomemo_models_load("../models", err, sizeof(err)) == 1);
  const phomemo_model_t *m08f = phomemo_model_find("m08f");
  assert(m08f);
  assert(!phomemo_model_find("q30"));
  assert(!strcmp(m08f->make_and_model, "Phomemo M08F"));
  assert(!strcmp(m08f->device_id, "MFG:Phomemo;MDL:M08F;CMD:PHOMEMO;"));
  assert(m08f->dpi == 203 && m08f->width_px == 1680);
  assert(m08f->top_margin == 1000 && m08f->bottom_margin == 500);
  assert(m08f->head_width == 21020);
  assert(m08f->num_media == 3 && m08f->default_media == 0);
  assert(!strcmp(m08f->media[0], "iso_a4_210x297mm"));
  assert(!strcmp(m08f->media[1], "iso_a5_148x210mm"));
  assert(!strcmp(m08f->media[2], "na_letter_8.5x11in"));
  assert(strstr(m08f->icons[2], "/m08f/icon-512.png") && !m08f->icon_data[2]);
  assert(phomemo_model_for_device_id("MFG:Phomemo;MDL:M08F;CMD:PHOMEMO;") ==
         m08f);
  assert(!phomemo_model_for_device_id("MFG:Phomemo;MDL:Q30;"));
  assert(phomemo_models_load("/nonexistent", err, sizeof(err)) == 0);
  assert(strstr(err, "/nonexistent"));
  assert(phomemo_models_load("../models", err, sizeof(err)) == 1);

  pappl_pr_options_t a5_portrait =
    options_for("iso_a5_148x210mm", 14800, 21000, 1182, 1678);
  pappl_pr_options_t a5_landscape =
    options_for("iso_a5_148x210mm", 14800, 21000, 1678, 1182);
  pappl_pr_options_t a4 =
    options_for("iso_a4_210x297mm", 21000, 29700, 1678, 2374);
  // Letter is wider than the head: the raster is 1725 px, the bridge keeps
  // its centre.
  pappl_pr_options_t letter =
    options_for("na_letter_8.5x11in", 21590, 27940, 1725, 2233);
  int head = m08f->head_width;
  assert(phomemo_should_rotate(&a5_portrait, head));
  assert(!phomemo_should_rotate(&a5_landscape, head));
  assert(!phomemo_should_rotate(&a4, head));
  assert(!phomemo_should_rotate(&letter, head));

  assert(phomemo_media_length_mm(&a4, head) == 297.0);
  assert(phomemo_media_length_mm(&a5_portrait, head) == 148.0);
  assert(phomemo_media_length_mm(&a5_landscape, head) == 148.0);
  assert(phomemo_media_length_mm(&letter, head) == 279.4);

  char info[64];
  phomemo_device_info(m08f, "AA:BB:CC:DD:EE:FF", info, sizeof(info));
  assert(!strcmp(info, "Phomemo M08F (DDEEFF)"));
  phomemo_device_info(m08f, "11:22:33:DD:EE:FF", info, sizeof(info));
  assert(!strcmp(info, "Phomemo M08F (DDEEFF)"));

  char model[32];
  assert(phomemo_uri_model("phomemo://AA-BB-CC-DD-EE-FF?model=m08f", model,
                           sizeof(model)));
  assert(!strcmp(model, "m08f"));
  assert(!phomemo_uri_model("phomemo://AA-BB-CC-DD-EE-FF", model,
                            sizeof(model)));

  puts("test_driver: ok");
  return 0;
}
