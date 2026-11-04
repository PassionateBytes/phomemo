# Model manifests

One directory per supported printer model, read by every part of
phomemo-driver: the library builds its profile from it, the bridge uses that
profile for each printer it connects to, and the printer app builds its PAPPL
driver (media, resolution, margins, names, icons) from it.

```
m08f/
  model.json      the model manifest
  icon-48.png     printer icons in the three sizes PAPPL uses
  icon-128.png
  icon-512.png
```

The directory name is the model's identifier (lower case, also the PAPPL
driver name). The field reference, how each part reads the manifests and a
step-by-step guide to adding a model are in the documentation:
[Printer models](https://passionatebytes.github.io/phomemo-driver/models.html).

**Contributions of new models are very welcome.** A Phomemo model that speaks
the same protocol needs only a new directory here: open a pull request with it
and a note on how you tested it.

Like the library that ships them, the model manifests are licensed under the
GNU LGPL, version 3 or later.
