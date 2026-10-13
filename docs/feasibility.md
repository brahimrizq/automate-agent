# Feasibility: static evidence, not a working-host claim

Inspection date: 2026-10-13. Source: the user's private x86-64 LTechAgent ZIP and
its matching extracted files. The archive, tenant values, encrypted templates,
and proprietary code are not included in this repository. Nothing from this
installer was executed during development or public CI.

## Verified by static inspection

| Item | Evidence and implication |
| --- | --- |
| Architecture | ELF64 little-endian x86-64 agent, shared library and updater. No ARM claim. A separate x86 installer exists but is outside this release. |
| Runtime | Agent links to `libltech.so`, glibc, libm and libdl. The library references GLIBC_2.28. No JVM dependency was found in the installer or core linked libraries. JRE/JDK sufficiency is therefore not a relevant verified requirement for this core package. |
| Start command | Supplied systemd unit uses `Type=simple`, working directory `/usr/local/ltechagent`, and `ExecStart=/usr/local/ltechagent/ltechagent` without flags. SIGTERM handling appears in binary diagnostics. Actual shutdown behavior is untested. |
| Installer | Copies agent, library, updater and uninstaller; writes `agent_config`; installs init/service definitions; starts the service. It also handles legacy migration and can log old identity information. The wrapper never invokes it. |
| Enrollment | Installer embeds server address, enrollment password and location ID. It creates configuration and starts the process; exact enrollment timing and server behavior need live testing. |
| State | Working-directory `state` stores computer identity/password; configuration, certificate cache, logs, templates and downloaded operational files are referenced. Preserve the entire dedicated directory pending a verified minimal state inventory. |
| TLS / updates | Static parsing confirms `ssl`, `ssl_verify_cert` and `auto_update` accept `yes`/`no`. The wrapper enforces certificate verification and requests no automatic updates. This does not prove all server-driven update paths honor the setting. |
| Updater | References `Linux/LTechAgent_x86_64.zip`, `/LabTech/Updates/`, `/usr/bin/unzip`, `/tmp/LTechAgent`, `bash ./install.sh`, and service stop/start commands. That process model is incompatible with an assumed drop-in init-free update. |
| Additional components | References remote transfer/config/app paths and optional dynamic libraries for D-Bus, kernel modules, printing, X11 and RPM. Their feature requirements are not established. They are not installed merely because their names appear. |

## Host discovery evidence

| Reported property | Observed input | Container limitation |
| --- | --- | --- |
| Hostname | `gethostname()` | Uses the container UTS namespace. |
| OS | `uname`, `/etc/os-release`, `/etc/system-release`, `lsb_release` | Kernel and user-space distribution may describe different environments. |
| CPU and memory | `/proc/cpuinfo`, `/proc/stat`, `/proc/meminfo`, SMBIOS interfaces | Visibility and cgroup limits must be compared with actual reported values. |
| Disks | `/sys/block`, `/proc/partitions`, `/proc/mounts`, `statvfs` | Devices and mount paths do not automatically match host mounts. |
| Processes | `/proc/<pid>/stat`, `exe`, `cmdline` | Isolated PID namespace cannot inventory host processes. |
| Services | systemd D-Bus interface references | No host service bus is exposed. A read-only socket mount would not make RPC read-only. |
| Packages | `/var/lib/dpkg/status`, `dpkg -L`, RPM database | Reports the container package database, not the host's. |
| Network | `/proc/net`, `/sys/class/net` | Bridge networking shows container interfaces and connections. |

These facts establish a concrete risk of incorrect host reports. They do not
establish that arbitrary namespace sharing can fix all reports. The default is
an experimental runtime harness, not a validated host-monitoring deployment.

## Assumptions and blockers

Ubuntu 24.04 amd64 is a candidate glibc runtime. Distribution support, enrollment,
server-forced updates, remote tasks, certificate behavior, and complete runtime
dependencies remain unverified. No disposable VM or test Automate location was
available. No host-access override is shipped without evidence.

Official ConnectWise Automate documentation was consulted where publicly indexed;
the [Automate installer page](https://docs.connectwise.com/ConnectWise_Automate_Documentation/090/090/020)
redirected to authenticated ConnectWise University access. Its indexed text lists
Linux x86 and x86_64 installers, not container support. Current distribution and
feature support could not be verified. ScreenConnect documentation is not used
as an Automate runtime requirement.
