# Fedora does not package bleak; phomemo needs it. Built in the
# phomemo-driver COPR project only.
%global pypi_name bleak

Name:           python-%{pypi_name}
Version:        3.0.2
Release:        1%{?dist}
Summary:        Cross-platform Bluetooth Low Energy client for Python

License:        MIT
URL:            https://github.com/hbldh/bleak
Source0:        %{pypi_source %{pypi_name}}

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
* Wed Nov 04 2026 Paul Bütof - 3.0.2-1
- Package for the phomemo-driver COPR project
