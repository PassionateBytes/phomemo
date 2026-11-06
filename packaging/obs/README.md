# Open Build Service

The OBS project `home:passionatebytes:phomemo-driver` on
[build.opensuse.org](https://build.opensuse.org) builds the Debian and
Ubuntu packages and, as an alternative to COPR, the Fedora RPMs. Each
subdirectory here holds the `_service` file of one OBS package; OBS keeps
its own copy (uploaded once with `osc`), everything else comes from this
repository at every service run.

| Package | Source | Targets |
|---|---|---|
| `phomemo-driver` | Newest `v*` tag: tarball (made on the server), `packaging/rpm/phomemo-driver.spec`, `packaging/debian/*` | All |
| `python-bleak` | `packaging/rpm/python-bleak.spec` from `main`, bleak sdist from PyPI | RPM targets only (Debian and Ubuntu ship `python3-bleak`) |

## Project setup

Once, by the project owner, with [`osc`](https://github.com/openSUSE/osc)
logged in (`osc` asks for the credentials on first use).

1. Create the project with its build targets:

   ```bash
   osc meta prj -e home:passionatebytes:phomemo-driver
   ```

   Project metadata (`<user>` is the OBS login; add or drop targets as
   distributions come and go, every Fedora target wants both packages,
   every Debian and Ubuntu target only `phomemo-driver`):

   ```xml
   <project name="home:passionatebytes:phomemo-driver">
     <title>Phomemo printer driver</title>
     <description>Printer driver for the Phomemo M08F thermal printer: PAPPL printer app and Bluetooth bridge. https://github.com/PassionateBytes/phomemo-driver</description>
     <person userid="<user>" role="maintainer"/>
     <repository name="Fedora_Rawhide">
       <path project="Fedora:Rawhide" repository="standard"/>
       <arch>x86_64</arch>
       <arch>aarch64</arch>
     </repository>
     <repository name="Fedora_44">
       <path project="Fedora:44" repository="standard"/>
       <arch>x86_64</arch>
       <arch>aarch64</arch>
     </repository>
     <repository name="Debian_Unstable">
       <path project="Debian:Next" repository="standard"/>
       <arch>x86_64</arch>
       <arch>aarch64</arch>
     </repository>
     <repository name="Debian_13">
       <path project="Debian:13" repository="update"/>
       <arch>x86_64</arch>
       <arch>aarch64</arch>
     </repository>
     <repository name="xUbuntu_26.04">
       <path project="Ubuntu:26.04" repository="universe"/>
       <arch>x86_64</arch>
       <arch>aarch64</arch>
     </repository>
     <repository name="xUbuntu_25.10">
       <path project="Ubuntu:25.10" repository="universe"/>
       <arch>x86_64</arch>
       <arch>aarch64</arch>
     </repository>
     <repository name="xUbuntu_24.04">
       <path project="Ubuntu:24.04" repository="universe"/>
       <arch>x86_64</arch>
       <arch>aarch64</arch>
     </repository>
   </project>
   ```

   Debian testing is left out: pappl is not in it (removed from forky,
   check `https://tracker.debian.org/pkg/pappl` before adding it back).

   The repository names are the directory names users see under
   `download.opensuse.org/repositories/home:/passionatebytes:/phomemo-driver/`
   and the ones `docs/installation.md` lists. The web UI's "Add from a
   Distribution" dialog creates the same entries.

2. Set the project configuration, which tells the resolver which of
   several providers to install:

   ```bash
   osc meta prjconf -e home:passionatebytes:phomemo-driver
   ```

   ```
   # Debian: libjpeg-dev is provided by two packages
   Prefer: libjpeg-dev
   ```

   A target that reports `have choice for X needed by Y: A B` wants another
   `Prefer:` line here.

3. Create the two packages and upload their service files:

   ```bash
   osc meta pkg -e home:passionatebytes:phomemo-driver phomemo-driver
   osc meta pkg -e home:passionatebytes:phomemo-driver python-bleak
   ```

   `phomemo-driver` needs only a title and description. `python-bleak` also
   disables the Debian and Ubuntu targets, which would otherwise fail for
   want of Debian packaging:

   ```xml
   <package name="python-bleak" project="home:passionatebytes:phomemo-driver">
     <title>python-bleak</title>
     <description>Bluetooth Low Energy client for Python, for the Fedora targets (Debian and Ubuntu ship python3-bleak).</description>
     <build>
       <disable repository="Debian_Unstable"/>
       <disable repository="Debian_13"/>
       <disable repository="xUbuntu_26.04"/>
       <disable repository="xUbuntu_25.10"/>
       <disable repository="xUbuntu_24.04"/>
     </build>
   </package>
   ```

   Then, from a checkout of this repository:

   ```bash
   osc checkout home:passionatebytes:phomemo-driver
   cd home:passionatebytes:phomemo-driver
   cp /path/to/phomemo-driver/packaging/obs/phomemo-driver/_service phomemo-driver/
   cp /path/to/phomemo-driver/packaging/obs/python-bleak/_service python-bleak/
   (cd phomemo-driver && osc add _service && osc commit -m "Source service")
   (cd python-bleak && osc add _service && osc commit -m "Source service")
   ```

   The commit runs the services on the server: the sources appear as
   `_service:*` files and the builds start.

   `phomemo-driver` checks out the newest `v*` tag. Until a release
   carries `packaging/debian/`, its service fails with
   `packaging/debian/phomemo-driver.dsc: No such file or directory`. For
   that first run, set `revision` in the OBS copy of
   `phomemo-driver/_service` to the branch that has the files (`main`
   once they are merged), commit, and set it back to `@PARENT_TAG@` after
   the next release. The version still comes from the newest tag.

4. Create the token the release workflow uses and store it in GitHub. The
   token is written to a file in your runtime directory, never shown:

   ```bash
   osc token --create --operation runservice > "$XDG_RUNTIME_DIR/obs-token.xml"
   sed -n 's/.*<data name="token">\(.*\)<\/data>.*/\1/p' "$XDG_RUNTIME_DIR/obs-token.xml" |
     gh secret set OBS_TOKEN --repo PassionateBytes/phomemo-driver
   shred -u "$XDG_RUNTIME_DIR/obs-token.xml"
   gh variable set OBS_PROJECT --repo PassionateBytes/phomemo-driver --body home:passionatebytes:phomemo-driver
   ```

   A token without a package binding may run the services of any package
   its owner can write; the workflows name the project and package in the
   request. `osc token` lists the tokens, `osc token --delete <ID>` revokes
   one.

5. Check a service run by hand before the first release:

   ```bash
   osc token --trigger <TOKEN> --operation runservice home:passionatebytes:phomemo-driver phomemo-driver
   osc results home:passionatebytes:phomemo-driver
   ```

## How a release reaches OBS

`release.yml` (job `obs`) posts to
`https://api.opensuse.org/trigger/runservice?project=<OBS_PROJECT>&package=phomemo-driver`
with the token; OBS runs `_service`, which checks out the newest `v*` tag.
`bleak.yml` does the same for `python-bleak` when `python-bleak.spec`
changes on `main`. Both skip with a warning while the secret or the
variable is unset.

## Checking the sources locally

The services run on the server; `osc service runall` runs them in a
package checkout when `obs-service-tar_scm`, `obs-service-recompress`
and `obs-service-download_files` are installed
(openSUSE packages of the same names). For the Debian side, `make deb` in
this repository assembles `debian/` from `packaging/debian/debian.*` the way
OBS's `debtransform` does and builds the packages with `dpkg-buildpackage`.
