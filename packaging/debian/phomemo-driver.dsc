Format: 3.0 (quilt)
Source: phomemo-driver
Binary: phomemo-driver, python3-phomemo
Architecture: any all
Version: 0.4.0-1
Maintainer: Paul Bütof <paul@passionate-bytes.com>
Homepage: https://github.com/PassionateBytes/phomemo-driver
Standards-Version: 4.7.0
Build-Depends: debhelper-compat (= 13), dh-sequence-python3, pybuild-plugin-pyproject, python3-all, python3-hatchling, python3-bleak (>= 0.21), python3-pil (>= 10.1), python3-pytest, python3-pytest-asyncio, libpappl-dev, libcjson-dev, libcups2-dev, pkgconf | pkg-config
Package-List:
 phomemo-driver deb text optional arch=any
 python3-phomemo deb python optional arch=all
