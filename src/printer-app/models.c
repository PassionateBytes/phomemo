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

// Printer models, read from the model descriptions the library shares.

#include "phomemo.h"

#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "cJSON.h"

static phomemo_model_t models[PHOMEMO_MAX_MODELS];
static int num_models;

static const int icon_sizes[3] = {48, 128, 512};

// Reads a whole file into a new string; NULL when it cannot be read.
static char *
read_file(const char *path)
{
  FILE *fp = fopen(path, "rb");
  if (!fp)
    return NULL;

  char *text = NULL;
  size_t size = 0;
  if (!fseek(fp, 0, SEEK_END))
  {
    long end = ftell(fp);
    if (end >= 0 && !fseek(fp, 0, SEEK_SET) && (text = malloc((size_t)end + 1)))
    {
      size = fread(text, 1, (size_t)end, fp);
      text[size] = '\0';
    }
  }
  fclose(fp);
  return text;
}

static const char *
string_of(const cJSON *object, const char *key)
{
  const cJSON *item = cJSON_GetObjectItemCaseSensitive(object, key);
  return cJSON_IsString(item) ? item->valuestring : NULL;
}

static bool
number_of(const cJSON *object, const char *key, double *value)
{
  const cJSON *item = cJSON_GetObjectItemCaseSensitive(object, key);
  if (!cJSON_IsNumber(item))
    return false;
  *value = item->valuedouble;
  return true;
}

// Parses the model.json text of model id into model; path names the
// description in messages. False with err set when it is unusable.
static bool
parse_model(const char *text, const char *id, const char *path,
            phomemo_model_t *model, char *err, size_t errsize)
{
  cJSON *json = cJSON_Parse(text);
  if (!json)
  {
    snprintf(err, errsize, "%s: not valid JSON", path);
    return false;
  }

  bool ok = false;
  const char *json_id = string_of(json, "id");
  const char *make = string_of(json, "make");
  const char *name = string_of(json, "name");
  const cJSON *media = cJSON_GetObjectItemCaseSensitive(json, "media");
  double dpi, width_px, top, bottom;

  memset(model, 0, sizeof(*model));
  model->default_media = -1;
  if (!json_id || strcmp(json_id, id))
    snprintf(err, errsize, "%s: id must be \"%s\"", path, id);
  else if (!make || !name)
    snprintf(err, errsize, "%s: make and name are required", path);
  else if (!number_of(json, "dpi", &dpi) ||
           !number_of(json, "print_width_px", &width_px) ||
           !number_of(json, "top_margin_mm", &top) ||
           !number_of(json, "bottom_margin_mm", &bottom) || dpi <= 0)
    snprintf(err, errsize,
             "%s: dpi, print_width_px and the margins must be numbers", path);
  else if (!cJSON_IsArray(media) || cJSON_GetArraySize(media) < 1 ||
           cJSON_GetArraySize(media) > PHOMEMO_MAX_MEDIA)
    snprintf(err, errsize, "%s: media must list 1 to %d sizes", path,
             PHOMEMO_MAX_MEDIA);
  else
  {
    snprintf(model->id, sizeof(model->id), "%s", id);
    snprintf(model->make_and_model, sizeof(model->make_and_model), "%s %s",
             make, name);
    snprintf(model->device_id, sizeof(model->device_id),
             "MFG:%s;MDL:%s;CMD:PHOMEMO;", make, name);
    model->dpi = (int)dpi;
    model->width_px = (int)width_px;
    model->head_width = (int)(width_px / dpi * 2540.0);
    model->top_margin = (int)(top * 100.0 + 0.5);
    model->bottom_margin = (int)(bottom * 100.0 + 0.5);

    const cJSON *entry;
    ok = true;
    cJSON_ArrayForEach(entry, media)
    {
      const char *pwg = string_of(entry, "pwg");
      if (!pwg)
      {
        snprintf(err, errsize, "%s: every media entry needs a pwg name", path);
        ok = false;
        break;
      }
      if (cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(entry, "default")))
        model->default_media = model->num_media;
      snprintf(model->media[model->num_media++], sizeof(model->media[0]), "%s",
               pwg);
    }
    if (ok && model->default_media < 0)
    {
      snprintf(err, errsize, "%s: one medium must be the default", path);
      ok = false;
    }
  }

  cJSON_Delete(json);
  return ok;
}

// Reads <dir>/<id>/model.json and the icon files next to it into model;
// false with err set when the description is unusable.
static bool
load_model(const char *dir, const char *id, phomemo_model_t *model, char *err,
           size_t errsize)
{
  char path[1024];
  snprintf(path, sizeof(path), "%s/%s/model.json", dir, id);
  char *text = read_file(path);
  if (!text)
  {
    snprintf(err, errsize, "%s: cannot be read", path);
    return false;
  }
  bool ok = parse_model(text, id, path, model, err, errsize);
  free(text);
  for (int i = 0; ok && i < 3; i++)
  {
    snprintf(model->icons[i], sizeof(model->icons[i]), "%s/%s/icon-%d.png",
             dir, id, icon_sizes[i]);
    if (access(model->icons[i], R_OK))
      model->icons[i][0] = '\0';
  }
  return ok;
}


static int
compare_ids(const void *a, const void *b)
{
  return strcmp(((const phomemo_model_t *)a)->id,
                ((const phomemo_model_t *)b)->id);
}

// Fills the table from the descriptions built into the binary.
static int
load_embedded(char *err, size_t errsize)
{
  char model_err[512] = "";
  num_models = 0;
  for (int i = 0;
       i < phomemo_num_embedded_models && num_models < PHOMEMO_MAX_MODELS; i++)
  {
    const phomemo_embedded_model_t *e = &phomemo_embedded_models[i];
    char where[64];
    snprintf(where, sizeof(where), "built-in %.32s model.json", e->id);
    phomemo_model_t *model = &models[num_models];
    if (!parse_model(e->json, e->id, where, model, model_err,
                     sizeof(model_err)))
    {
      fprintf(stderr, "phomemo-printer-app: %s\n", model_err);
      continue;
    }
    for (int j = 0; j < 3; j++)
    {
      model->icon_data[j] = e->icons[j].data;
      model->icon_len[j] = e->icons[j].len;
    }
    num_models++;
  }
  qsort(models, (size_t)num_models, sizeof(models[0]), compare_ids);
  if (!num_models)
    snprintf(err, errsize, "no usable built-in model descriptions%s%s",
             model_err[0] ? ": " : "", model_err);
  return num_models;
}

int
phomemo_models_load(const char *dir, char *err, size_t errsize)
{
  if (!dir)
  {
    const char *env = getenv("PHOMEMO_MODELS_DIR");
    if (!env || !*env)
      return load_embedded(err, errsize);
    dir = env;
  }

  num_models = 0;
  DIR *listing = opendir(dir);
  if (!listing)
  {
    snprintf(err, errsize, "no model descriptions in %s", dir);
    return 0;
  }

  struct dirent *entry;
  char model_err[1400] = "";
  while ((entry = readdir(listing)) && num_models < PHOMEMO_MAX_MODELS)
  {
    char path[1024];
    if (entry->d_name[0] == '.')
      continue;
    snprintf(path, sizeof(path), "%s/%s/model.json", dir, entry->d_name);
    if (access(path, F_OK))
      continue;
    if (strlen(entry->d_name) >= sizeof(models[0].id))
      continue;
    if (load_model(dir, entry->d_name, &models[num_models], model_err,
                   sizeof(model_err)))
      num_models++;
    else
      fprintf(stderr, "phomemo-printer-app: %s\n", model_err);
  }
  closedir(listing);

  qsort(models, (size_t)num_models, sizeof(models[0]), compare_ids);
  if (!num_models)
    snprintf(err, errsize, "no usable model descriptions in %s%s%s", dir,
             model_err[0] ? ": " : "", model_err);
  return num_models;
}

int
phomemo_models_count(void)
{
  return num_models;
}

const phomemo_model_t *
phomemo_model_at(int index)
{
  return index >= 0 && index < num_models ? &models[index] : NULL;
}

const phomemo_model_t *
phomemo_model_find(const char *id)
{
  for (int i = 0; id && i < num_models; i++)
    if (!strcmp(models[i].id, id))
      return &models[i];
  return NULL;
}

const phomemo_model_t *
phomemo_model_for_device_id(const char *device_id)
{
  for (int i = 0; device_id && i < num_models; i++)
    if (!strcmp(models[i].device_id, device_id))
      return &models[i];
  return NULL;
}

bool
phomemo_uri_model(const char *device_uri, char *buffer, size_t bufsize)
{
  const char *query = device_uri ? strchr(device_uri, '?') : NULL;
  const char *value = NULL;
  for (const char *p = query; p; p = strchr(p + 1, '&'))
    if (!strncmp(p + 1, "model=", 6))
      value = p + 7;
  if (!value || !*value)
    return false;
  size_t len = strcspn(value, "&#");
  if (len >= bufsize)
    return false;
  memcpy(buffer, value, len);
  buffer[len] = '\0';
  return true;
}
