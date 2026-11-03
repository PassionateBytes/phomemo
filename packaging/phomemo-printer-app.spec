Name:           phomemo-printer-app
Version:        0.1.0
Release:        1%{?dist}
Summary:        IPP Everywhere printer application for the Phomemo M08F

License:        LGPL-3.0-or-later AND MIT
URL:            https://github.com/PassionateBytes/phomemo-driver
Source0:        %{url}/archive/v%{version}/phomemo-driver-%{version}.tar.gz

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  pkgconf-pkg-config
BuildRequires:  pappl-devel
BuildRequires:  cups-devel
BuildRequires:  systemd-rpm-macros
Requires:       python3-phomemo >= %{version}
Requires:       avahi
Requires:       cups
Recommends:     cups-browsed

%description
A PAPPL printer application that presents the Phomemo M08F A4 thermal
printer as an IPP Everywhere printer, so CUPS and other IPP clients print
to it like to any other printer. The Bluetooth side is phomemo-bridge from
the python3-phomemo package.

%prep
%autosetup -n phomemo-driver-%{version}

%build
%make_build -C printer-app CFLAGS="%{build_cflags}" LDFLAGS="%{build_ldflags}"

%install
%make_install -C printer-app PREFIX=%{_prefix} UNITDIR=%{_unitdir} PRESETDIR=%{_presetdir}

%check
%make_build -C printer-app test CFLAGS="%{build_cflags}" LDFLAGS="%{build_ldflags}"

%post
%systemd_post phomemo-printer-app.service

%preun
%systemd_preun phomemo-printer-app.service

%postun
%systemd_postun_with_restart phomemo-printer-app.service

%files
%doc printer-app/README.md
%license printer-app/third_party/cJSON.LICENSE
%{_bindir}/phomemo-printer-app
%{_unitdir}/phomemo-printer-app.service
%{_presetdir}/90-phomemo-printer-app.preset

%changelog
* Mon Nov 03 2026 Paul Bütof - 0.1.0-1
- First package
