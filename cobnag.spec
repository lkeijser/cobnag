%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
Name:           cobnag
Version:        1.0.1
Release:        1%{?dist}
Summary:        Generate Nagios configuration files based on a Cobbler profile

Group:          Applications/Internet
License:        GPL
URL:            git://github.com/lkeijser/cobnag.git
Source0:        cobnag-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:      noarch

Requires:      python python-configobj nagios

%description
Cobnag can generate Nagios configuration files for a system by 
making an XMLRPC connection to a Cobbler server, read what profile
is attached to it and matches services (defined in a seperate
configuration file) to it. 

%prep
%setup -q


%build


%install
rm -rf $RPM_BUILD_ROOT
install -D -p -m 0755 cobnag %{buildroot}/usr/bin/cobnag
install -D -p -m 0644 cobnag.conf %{buildroot}/etc/cobnag.conf
install -D -p -m 0644 app.py %{buildroot}/%{python_sitelib}/cobnag/app.py
install -D -p -m 0644 __init__.py %{buildroot}/%{python_sitelib}/cobnag/__init__.py


%clean
rm -rf $RPM_BUILD_ROOT


%files
%defattr(-,root,root,-)
%dir %{python_sitelib}/cobnag
%{python_sitelib}/cobnag/*.py*
/etc/cobnag.conf
/usr/bin/cobnag
%doc ChangeLog README COPYING



%changelog
* Tue Jun 2 2009 Léon Keijser <keijser@stone-it.com> - 1.0-1
- initial release
