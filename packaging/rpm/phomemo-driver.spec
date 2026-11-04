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

Name:           phomemo-driver
Version:        0.1.0
Release:        2%{?dist}
Summary:        Printer driver for the Phomemo M08F thermal printer

License:        GPL-3.0-or-later AND MIT
URL:            https://github.com/PassionateBytes/phomemo-driver
Source0:        %{url}/archive/v%{version}/phomemo-driver-%{version}.tar.gz

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  pkgconf-pkg-config
BuildRequires:  pappl-devel
BuildRequires:  cups-devel
BuildRequires:  python3-devel
BuildRequires:  systemd-rpm-macros

Requires:       python3-phomemo = %{version}-%{release}
Requires:       avahi
Requires:       bluez
Requires:       cups
Recommends:     cups-browsed

%description
Makes the Phomemo M08F A4 thermal printer a printer like any other: a PAPPL
printer application presents it to CUPS and other IPP clients, and the
phomemo-bridge service owns its Bluetooth Low Energy link. Both run as
system services, enabled on installation.

%package -n python3-phomemo
Summary:        Python library and bridge daemon for Phomemo thermal printers
License:        LGPL-3.0-or-later
BuildArch:      noarch

%description -n python3-phomemo
Async Python library for Phomemo thermal printers over Bluetooth Low Energy
(M08F A4): discovery, raster printing, sensor events. Includes
phomemo-bridge, the daemon that owns the printer link for the printer
application.

%prep
%autosetup -n phomemo-driver-%{version}

%generate_buildrequires
cd packages/phomemo
%pyproject_buildrequires

%build
%make_build -C printer-app CFLAGS="%{build_cflags}" LDFLAGS="%{build_ldflags}"
cd packages/phomemo
%pyproject_wheel

%install
%make_install -C printer-app PREFIX=%{_prefix} UNITDIR=%{_unitdir} PRESETDIR=%{_presetdir}
cd packages/phomemo
%pyproject_install
%pyproject_save_files -l phomemo
cd ../..
install -D -m 644 packaging/systemd/phomemo-bridge.service %{buildroot}%{_unitdir}/phomemo-bridge.service
install -D -m 644 packaging/systemd/phomemo.sysusers.conf %{buildroot}%{_sysusersdir}/phomemo.conf
install -D -m 644 packaging/systemd/90-phomemo-bridge.preset %{buildroot}%{_presetdir}/90-phomemo-bridge.preset
install -D -m 644 packaging/config/bridge.toml %{buildroot}%{_sysconfdir}/phomemo/bridge.toml

%check
%make_build -C printer-app test CFLAGS="%{build_cflags}" LDFLAGS="%{build_ldflags}"
cd packages/phomemo
%pyproject_check_import

%post
%systemd_post phomemo-bridge.service phomemo-printer-app.service
# Start the services on first installation so the printer works right
# away; upgrades restart them in %%postun. Skipped where systemd is not
# running (image and container builds).
if [ $1 -eq 1 ] && [ -d /run/systemd/system ]; then
    systemctl start phomemo-bridge.service phomemo-printer-app.service >/dev/null 2>&1 || :
fi

%preun
%systemd_preun phomemo-printer-app.service phomemo-bridge.service

%postun
%systemd_postun_with_restart phomemo-bridge.service phomemo-printer-app.service

%files
%doc README.md printer-app/README.md
%license printer-app/COPYING printer-app/third_party/cJSON.LICENSE
%{_bindir}/phomemo-printer-app
%{_unitdir}/phomemo-printer-app.service
%{_unitdir}/phomemo-bridge.service
%{_presetdir}/90-phomemo-printer-app.preset
%{_presetdir}/90-phomemo-bridge.preset
%{_sysusersdir}/phomemo.conf
%dir %{_sysconfdir}/phomemo
%config(noreplace) %{_sysconfdir}/phomemo/bridge.toml

%files -n python3-phomemo -f %{pyproject_files}
%doc packages/phomemo/README.md
%license packages/phomemo/COPYING packages/phomemo/COPYING.LESSER
%{_bindir}/phomemo-bridge

%changelog
* Wed Nov 04 2026 Paul Bütof - 0.1.0-2
- Start the services on first installation
- Register printers in range when the system service starts

* Tue Nov 03 2026 Paul Bütof - 0.1.0-1
- First package
