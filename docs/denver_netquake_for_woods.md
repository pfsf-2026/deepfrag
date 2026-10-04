# Denver NetQuake server: notes for woods

Your QSS-M server moved from the old AWS box to a new machine in Denver on 2026-09-29. Same files, same
port, same launch flags. Two things are different: where the files live, and how the server is started.

## Getting in

Peter will send you a private key file named `woods_den`. Save it, then:

```bash
chmod 600 woods_den
ssh -i woods_den woods@den.qwsrv.com
```

The address is `70.39.95.254` if the name does not resolve. Login is by key only; your account has no
password. `denver.quakeone.com` already points at this machine.

## Where everything is

| What | Where |
|---|---|
| Your game directory | `~/qssm` (a link to `/opt/qw/qssm`) |
| Server binary | `~/qssm/QSS-M-l64` |
| Config, maps, paks, progs | `~/qssm/id1/` (`server.cfg`, `configs/`, `maps/`, `progs.dat`, the pak files) |
| TLS files | `~/qssm/privkey.pem`, `~/qssm/fullchain.pem` |
| Port | 26000, TCP and UDP |

You own the whole directory and can edit, add and replace anything in it.

## How it runs now

The machine is Debian 12. Your binary was built on Debian 13 and needs newer system libraries, so it runs
inside a small Debian 13 container. In practice that changes very little:

- The container only supplies the libraries. Your game directory is the real directory on the machine,
  shared into the container, so editing a file in `~/qssm` is editing the live server's file.
- The container uses the machine's network directly. Port 26000 is the machine's port 26000.
- It is started by systemd as a service called `qssm`, with exactly your old command line:
  `./QSS-M-l64 -useice -privkey privkey.pem -pubkey fullchain.pem -dedicated -port 26000 -protocol 666 +developer 0`
- If the server exits or crashes it is restarted after 10 seconds.
- It restarts every Sunday at 05:00 Pacific, the same schedule as your old cron job.
- The server process runs as a service user named `qw`, not as you.

## Day to day

```bash
systemctl status qssm            # is it up, since when
sudo systemctl restart qssm      # restart it
sudo systemctl stop qssm         # stop it
sudo systemctl start qssm        # start it
journalctl -u qssm -f            # follow the server's console output
journalctl -u qssm -n 200        # last 200 lines
```

Those three `sudo` commands are the only ones your account can run as root. There is no interactive server
console; use rcon from a client for live commands, and the journal for output.

**Changing a config or a map:** edit the file in `~/qssm/id1/`, then restart if the change needs it.

**Replacing the binary:** copy the new build over `~/qssm/QSS-M-l64`, keep it executable, restart. If a new
build needs a library the container does not have, the server will fail to start and the journal will name
the missing library. Tell Peter and the container gets rebuilt with it.

## Do not use the old scripts

`restart.sh`, `restart2.sh`, `new.sh`, `kill.sh` and `weekly-restart.txt` came over with the files but are not
used. Run directly on this machine, the binary will not start, because the libraries it needs only exist in
the container. systemd already does what those scripts did.

## Things that need Peter

- **The launch flags.** The command line lives in the service definition, which is owned by root.
- **The TLS certificate.** `fullchain.pem` is for `denver.quakeone.com` and **expired on 2026-08-29**. Your
  old `new.sh` renewed it automatically; nothing renews it here yet, and renewing needs root. If you get new
  files some other way, drop them in as `privkey.pem` and `fullchain.pem` and restart. Otherwise ask Peter
  to set up renewal.
- **Opening another port.** Only 26000 is open for this server.
- **Rebuilding the container**, as above.

## Things to know

- The journal currently repeats `Unable to listen on / - name already taken` about twice a minute. It was
  doing that before your account existed; it is yours to judge.
- Files the server writes itself belong to the `qw` user. If you ever get "permission denied" changing one,
  replace the file instead of editing it in place, or ask Peter.
- This machine also runs the DeepFrag QuakeWorld servers under `/opt/qw/nquakesv` and another admin's match
  agent. Your account cannot change those, and please leave them alone.
- Demos and other files outside `~/qssm` are not yours to clean up, even if the disk looks full. Ask first.
