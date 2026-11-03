%global srcname phomemo

Name:           python-%{srcname}
Version:        0.1.0
Release:        1%{?dist}
Summary:        Driver library and bridge daemon for Phomemo thermal printers

License:        LGPL-3.0-or-later
URL:            https://github.com/PassionateBytes/phomemo-driver
Source0:        %{url}/archive/v%{version}/phomemo-driver-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  systemd-rpm-macros

%global _description %{expand:
Async Python library for Phomemo thermal printers over Bluetooth Low Energy
(M08F A4), and phomemo-bridge, the daemon that owns the printer link for the
phomemo-printer-app printer application: it waits for sheets, converts pages
and prints them, and takes commands over a unix socket.}

%description %_description

%package -n python3-%{srcname}
Summary:        %{summary}
Requires:       bluez
%description -n python3-%{srcname} %_description

%prep
%autosetup -n phomemo-driver-%{version}

%generate_buildrequires
cd packages/phomemo
%pyproject_buildrequires

%build
cd packages/phomemo
%pyproject_wheel

%install
cd packages/phomemo
%pyproject_install
%pyproject_save_files -l phomemo
cd ../..
install -D -m 644 packaging/phomemo-bridge.service %{buildroot}%{_unitdir}/phomemo-bridge.service
install -D -m 644 packaging/phomemo.sysusers.conf %{buildroot}%{_sysusersdir}/phomemo.conf
install -D -m 644 packaging/90-phomemo-bridge.preset %{buildroot}%{_presetdir}/90-phomemo-bridge.preset
install -D -m 644 packaging/bridge.toml %{buildroot}%{_sysconfdir}/phomemo/bridge.toml

%check
cd packages/phomemo
%pyproject_check_import

%post -n python3-%{srcname}
%systemd_post phomemo-bridge.service

%preun -n python3-%{srcname}
%systemd_preun phomemo-bridge.service

%postun -n python3-%{srcname}
%systemd_postun_with_restart phomemo-bridge.service

%files -n python3-%{srcname} -f %{pyproject_files}
%doc packages/phomemo/README.md
%{_bindir}/phomemo-bridge
%{_unitdir}/phomemo-bridge.service
%{_sysusersdir}/phomemo.conf
%{_presetdir}/90-phomemo-bridge.preset
%dir %{_sysconfdir}/phomemo
%config(noreplace) %{_sysconfdir}/phomemo/bridge.toml

%changelog
* Mon Nov 03 2026 Paul Bütof - 0.1.0-1
- First package
