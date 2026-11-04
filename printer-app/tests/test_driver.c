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

  pappl_pr_options_t a5_portrait =
    options_for("iso_a5_148x210mm", 14800, 21000, 1182, 1678);
  pappl_pr_options_t a5_landscape =
    options_for("iso_a5_148x210mm", 14800, 21000, 1678, 1182);
  pappl_pr_options_t a4 =
    options_for("iso_a4_210x297mm", 21000, 29700, 1678, 2374);
  assert(phomemo_should_rotate(&a5_portrait));
  assert(!phomemo_should_rotate(&a5_landscape));
  assert(!phomemo_should_rotate(&a4));

  assert(phomemo_media_length_mm(&a4) == 297.0);
  assert(phomemo_media_length_mm(&a5_portrait) == 148.0);
  assert(phomemo_media_length_mm(&a5_landscape) == 148.0);

  char info[64];
  phomemo_device_info("AA:BB:CC:DD:EE:FF", info, sizeof(info));
  assert(!strcmp(info, "Phomemo M08F (DD:EE:FF)"));
  phomemo_device_info("11:22:33:DD:EE:FF", info, sizeof(info));
  assert(!strcmp(info, "Phomemo M08F (DD:EE:FF)"));

  puts("test_driver: ok");
  return 0;
}
