# Erster Labortest (v0.0.2)

Noch kein betriebsbereites HAOS. Ziel: originaler HAOS-Userspace mit systemd in einem isolierten, unprivilegierten CT. Keine produktive Infrastruktur verwenden. Empfohlen: wegwerfbare Linux-VM als Build-Worker und separater PVE-Testhost (auch als Lab-VM möglich). Keine Host-Geräte oder Host-Verzeichnisse durchreichen. Keine AppArmor-Abschaltung, kein Nesting für diesen Test.

## A. Originalimage extrahieren (Build-Worker)

    sudo apt update
    sudo apt install python3-guestfs libguestfs-tools xz-utils git

Aktualisiert Paketliste und installiert die Werkzeuge für schreibgeschützte Disk-Image-Analyse. Der libguestfs-Appliance-Kernel muss EROFS unterstützen. Bei Fehlern nicht auf Host-Loop-Mounts ausweichen.

    git clone https://github.com/x3muha/HAOS-LXC.git
    cd HAOS-LXC

Holt den Quellcode. Lade das offizielle generische x86-64 Raw-Image der Version 18.4 sowie SHA256SUMS und SHA256SUMS.sigstore.json von https://github.com/home-assistant/operating-system/releases/tag/18.4 herunter. Prüfe die signierten Prüfsummen mit Cosign nach der offiziellen Release-Anleitung (Identität/Issuer prüfen), anschließend die Prüfsumme der konkreten .img.xz-Datei. Eine lokal berechnete Prüfsumme alleine ist kein Herkunftsnachweis. Ohne erfolgreich verifiziertes Original nicht fortfahren.

    xz -dk haos_generic-x86-64-18.4.img.xz
    sha256sum haos_generic-x86-64-18.4.img

Entpackt das verifizierte Image und ermittelt den Hash für den Extraktor. RAW_SHA256 durch den so ermittelten 64-stelligen Wert ersetzen.

    /usr/bin/python3 tools/extract_rootfs.py haos_generic-x86-64-18.4.img --sha256 RAW_SHA256 --output out/slot-a
    python3 tools/audit_rootfs.py out/slot-a/rootfs.tar.gz > out/audit.json
    sha256sum out/slot-a/rootfs.tar.gz

Extrahiert den System-Slot schreibgeschützt, erstellt die Unit-Inventur und ermittelt die Prüfsumme des Rootfs. Kein Overlay oder Daten-Image wird übernommen. Die Ausgabe ist noch nicht bootfähig. ROOTFS_SHA256 durch die ermittelte Prüfsumme ersetzen.

    python3 tools/prepare_probe.py out/slot-a/rootfs.tar.gz --sha256 ROOTFS_SHA256 --output out/probe

Baut ein ausschließlich für den Boot-Probe vorgesehenes Template. Prüfe beide Manifeste und die Inventur. Der Build kann auf unbekannten Archivstrukturen absichtlich abbrechen. Keine Prüfungen umgehen. Der Boot-Probe hat keinen SSH-/Netzwerkdienst.

## B. Proxmox-Lab

Übertrage nur das lokal erstellte Template auf den isolierten Testhost in einen Storage mit Content-Typ Container template (Beispiel: local:vztmpl). Prüfsumme nach Übertragung vergleichen. CTID und Storage unten sind Beispiele: erst eine freie ID im Cluster sowie passenden lokalen Test-Storage verifizieren. Keine bestehenden CTs überschreiben.

    pct create 9900 local:vztmpl/haos-lxc-probe.tar.gz --ostype unmanaged --unprivileged 1 --rootfs local-lvm:8 --cores 2 --memory 2048 --swap 0 --onboot 0
    pct config 9900
    pct start 9900 --debug

Erstellt einen frischen CT ohne Netzwerk, Nesting oder Host-Geräte, prüft die Konfiguration, startet mit Debug-Ausgabe. PVE soll keine distributionsspezifische Einrichtung vornehmen. Bei unerwarteten Mounts, Privilegien oder Fehlern stoppen.

    pct exec 9900 -- cat /proc/1/comm
    pct exec 9900 -- cat /proc/1/uid_map
    pct exec 9900 -- cat /run/haos-lxc/boot-ok
    pct exec 9900 -- systemctl list-units --state=active --no-pager
    pct exec 9900 -- systemctl --failed --no-pager

Prüft PID 1, UID-Mapping, den Marker sowie aktive/fehlgeschlagene Units. Erwartet: systemd, nicht-identisches Host-UID-Mapping, boot-ok, keine unerwarteten upstream Dienste. Der Marker beweist noch keinen produktiven HAOS-Betrieb. Falls systemctl ohne D-Bus nicht funktioniert, Fehler protokollieren. Keine Netzwerkverbindung hinzufügen.

    pct stop 9900

Stoppt ausschließlich den zuvor erzeugten Wegwerf-CT. Normaler Shutdown kann im reduzierten Profil fehlen. Keine produktiven Daten in diesem CT.

## Rückmeldung

In ein Issue: PVE-Version (pveversion -v), uname -r, redigierte CT-Konfiguration, beide Manifeste, audit.json, vollständige Fehlermeldungen/Debug-Ausgabe, Resultat der fünf Probe-Befehle und Storage-Typ. Keine Images oder privaten Daten hochladen. Bei fehlgeschlagenem Build bereits dort abbrechen.
