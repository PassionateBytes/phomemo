# This file is part of phomemo-driver.
# Copyright (C) 2026 Paul Bütof, Passionate Bytes Solutions
#
# phomemo-driver is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# phomemo-driver is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with phomemo-driver.  If not, see <https://www.gnu.org/licenses/>.

# Fedora does not package bleak; phomemo needs it. Built in the
# phomemo-driver COPR and OBS projects at the version named below, which
# Renovate bumps from PyPI. Source0 spells out the PyPI URL (what the
# Fedora pypi_source macro expands to) because the OBS download service
# expands no Fedora macros.
%global pypi_name bleak

Name:           python-%{pypi_name}
Version:        3.0.1
Release:        1%{?dist}
Summary:        Cross-platform Bluetooth Low Energy client for Python

License:        MIT
URL:            https://github.com/hbldh/bleak
Source0:        https://files.pythonhosted.org/packages/source/b/%{pypi_name}/%{pypi_name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel

%global _description %{expand:
Bleak is a GATT client for Bluetooth Low Energy devices, built on asyncio.
On Linux it talks to BlueZ over D-Bus.}

%description %_description

%package -n python3-%{pypi_name}
Summary:        %{summary}
Requires:       bluez

%description -n python3-%{pypi_name} %_description

%prep
%autosetup -n %{pypi_name}-%{version}

%generate_buildrequires
# Runtime requirements without extras: the "pythonista" extra (iOS) has no
# Fedora package.
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l %{pypi_name}

%check
# The other backends (Windows, macOS, Android, iOS) import platform
# libraries that do not exist here.
%pyproject_check_import -e 'bleak.backends.winrt*' -e 'bleak.backends.corebluetooth*' -e 'bleak.backends.p4android*' -e 'bleak.backends.pythonista*'

%files -n python3-%{pypi_name} -f %{pyproject_files}
%doc README.rst

%changelog
* Wed Nov 04 2026 Paul Bütof - 3.0.1-1
- Package for the phomemo-driver COPR project (version follows uv.lock)
