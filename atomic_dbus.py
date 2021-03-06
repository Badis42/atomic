#!/usr/bin/python -Es

import dbus
import time
import threading
import dbus.service
import dbus.mainloop.glib
import json
from gi.repository import GLib # pylint: disable=no-name-in-module
import slip.dbus.service
from Atomic import Atomic
from Atomic.verify import Verify
from Atomic.images import Images
from Atomic.storage import Storage
from Atomic.diff import Diff
from Atomic.scan import Scan
from Atomic.ps import Ps

class atomic_dbus(slip.dbus.service.Object):
    default_polkit_auth_required = "org.atomic.readwrite"

    class Args():
        def __init__(self):
            self.image = None
            self.recurse = False
            self.debug = False
            self.devices = None
            self.driver = None
            self.graph = None
            self.force = None
            self.import_location = None
            self.export_location = None
            self.compares = []
            self.json = False
            self.no_files = False
            self.names_only = False
            self.rpms = False
            self.verbose = False
            self.scan_targets = []
            self.scanner = None
            self.scan_type = None
            self.list = False
            self.rootfs = []
            self.all = False
            self.images = False
            self.containers = False
            self.container = False
            self.prune = False
            self.heading = False
            self.truncate = False

    def __init__(self, *p, **k):
        super(atomic_dbus, self).__init__(*p, **k)
        self.atomic = Atomic()
        self.tasks = []
        self.tasks_lock = threading.Lock()
        self.last_token = 0
        self.scheduler_thread = threading.Thread(target = self.Scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        self.results = dict()
        self.results_lock = threading.Lock()

    def Scheduler(self):
        while True:
            current_task = None
            with self.tasks_lock:
                if(len(self.tasks) > 0):
                    current_task = self.tasks.pop(0)
            if current_task is not None:
                result = current_task[1].scan()
                with self.results_lock:
                    self.results[current_task[0]] = result
            time.sleep(1)

    def AllocateToken(self):
        with self.tasks_lock:
            self.last_token += 1
            return self.last_token

    # The Version method takes in an image name and returns its version
    # information
    @slip.dbus.polkit.require_auth("org.atomic.read")
    @dbus.service.method("org.atomic", in_signature='asb',
                         out_signature='aa{sv}')
    def Version(self, images, recurse=False):
        versions = []
        for image in images:
            args = self.Args()
            args.image = image
            args.recurse = recurse
            self.atomic.set_args(args)
            versions.append({"Image": image,
                             "Version": self.atomic.version()})
        return versions

    # The Verify method takes in an image name and returns whether or not the
    # image should be updated
    @slip.dbus.polkit.require_auth("org.atomic.read")
    @dbus.service.method("org.atomic", in_signature='as', out_signature='s')
    def Verify(self, images):
        verifications = []
        verify = Verify()
        verify.useTTY = False
        for image in images:
            args = self.Args()
            args.image = image
            verify.set_args(args)
            verifications.append({"Image": image,
                                  "Verification": verify.verify()}) #pylint: disable=no-member
        return json.dumps(verifications)

    # The StorageReset method deletes all containers and images from a system.
    # Resets storage to its initial configuration.
    @slip.dbus.polkit.require_auth("org.atomic.readwrite")
    @dbus.service.method("org.atomic", in_signature='', out_signature='')
    def StorageReset(self):
        storage = Storage()
        # No arguments are passed for storage_reset function
        args = self.Args()
        storage.set_args(args)
        storage.reset()

    # The StorageImport method imports all containers and their associated
    # contents from a filesystem directory.
    @slip.dbus.polkit.require_auth("org.atomic.readwrite")
    @dbus.service.method("org.atomic", in_signature='ss', out_signature='')
    def StorageImport(self, graph, import_location):
        storage = Storage()
        args = self.Args()
        args.graph = graph
        args.import_location = import_location
        storage.set_args(args)
        storage.Import()

    # The StorageExport method exports all containers and their associated
    # contents into a filesystem directory.
    @slip.dbus.polkit.require_auth("org.atomic.readwrite")
    @dbus.service.method("org.atomic", in_signature='ssb', out_signature='')
    def StorageExport(self, graph="/var/lib/docker", export_location="/var/lib/atomic/migrate", force = False):
        storage = Storage()
        args = self.Args()
        args.graph = graph
        args.export_location = export_location
        args.force = force
        storage.set_args(args)
        storage.Export()

    # The StorageModify method modifies the default storage setup.
    @slip.dbus.polkit.require_auth("org.atomic.readwrite")
    @dbus.service.method("org.atomic", in_signature='asv', out_signature='')
    def StorageModify(self, devices=None, driver = None):
        storage = Storage()
        args = self.Args()
        if devices:
            args.devices = devices
        else:
            args.devices = []
        args.driver = driver
        storage.set_args(args)
        storage.modify()

    # The Diff method shows differences between two container images, file
    # diff or RPMS.
    @slip.dbus.polkit.require_auth("org.atomic.read")
    @dbus.service.method("org.atomic", in_signature='ss',
                         out_signature='s')
    def Diff(self, first, second):
        diff = Diff()
        args = self.Args()
        args.compares = [first, second]
        args.json = True
        args.no_files = False
        args.names_only = False
        args.rpms = True
        args.verbose = True
        diff.set_args(args)
        return diff.diff()

    # The ScanList method will return a list of all scanners.
    @slip.dbus.polkit.require_auth("org.atomic.read")
    @dbus.service.method("org.atomic", in_signature='',
                         out_signature= 's')
    def ScanList(self):
        scan_list = Scan()
        args = self.Args()
        scan_list.set_args(args)
        return scan_list.get_scanners_list()

    # The ScanSetup method will create the scan object.
    def _ScanSetup(self, scan_targets, scanner, scan_type, rootfs, _all, images, containers):
        scan = Scan()
        args = self.Args()
        scan.useTTY = False
        if scan_targets:
            args.scan_targets = scan_targets
        if scanner:
            args.scanner = scanner
        if scan_type:
            args.scan_type = scan_type
        if len(scan_targets):
            args.scan_targets = scan_targets
        args.rootfs = rootfs
        args.all = _all
        args.images = images
        args.containers = containers
        scan.set_args(args)
        return scan


    # The Scan method will return a string.
    @slip.dbus.polkit.require_auth("org.atomic.read")
    @dbus.service.method("org.atomic", in_signature='asssasbbb',
                         out_signature= 's')
    def Scan(self, scan_targets, scanner, scan_type, rootfs, _all, images, containers):
        return self._ScanSetup(scan_targets, scanner, scan_type, rootfs, _all, images, containers).scan()

    # The ScheduleScan method will return a token.
    @slip.dbus.polkit.require_auth("org.atomic.read")
    @dbus.service.method("org.atomic", in_signature='asssasbbb',
                         out_signature= 'x')
    def ScheduleScan(self, scan_targets, scanner, scan_type, rootfs, _all, images, containers):
        scan = self._ScanSetup(scan_targets, scanner, scan_type, rootfs, _all, images, containers)
        token = self.AllocateToken()
        with self.tasks_lock:
            self.tasks.append((token, scan))
        return token

    # The GetScanResults method will determine whether or not the results for
    # the token are ready.
    @slip.dbus.polkit.require_auth("org.atomic.read")
    @dbus.service.method("org.atomic", in_signature='x',
                         out_signature= 's')
    def GetScanResults(self, token):
        with self.results_lock:
            if token in self.results:
                ret = self.results[token]
                del self.results[token]
                return ret
            else:
                return ""

    # The Update method downloads the latest container image.
    @slip.dbus.polkit.require_auth("org.atomic.readwrite")
    @dbus.service.method("org.atomic", in_signature='s', out_signature='')
    def Update(self, image):
        args = self.Args()
        args.image = image
        self.atomic.set_args(args)
        self.atomic.update()

    # The Images method will list all installed container images on the system.
    @slip.dbus.polkit.require_auth("org.atomic.read")
    @dbus.service.method("org.atomic", in_signature='', out_signature='s')
    def Images(self):
        args = self.Args()
        images = Images()
        images.set_args(args)
        return json.dumps(images.images())

    # The Vulnerable method will send back information that says
    # whether or not an installed container image is vulnerable
    @slip.dbus.polkit.require_auth("org.atomic.read")
    @dbus.service.method("org.atomic", in_signature='', out_signature='s')
    def VulnerableInfo(self):
        args = self.Args()
        self.atomic.set_args(args)
        return self.atomic.get_all_vulnerable_info()

    # The Ps method will list all containers on the system.
    @slip.dbus.polkit.require_auth("org.atomic.read")
    @dbus.service.method("org.atomic", in_signature='', out_signature='s')
    def Ps(self):
        ps = Ps()
        ps.useTTY = False
        args = self.Args()
        ps.set_args(args)
        return json.dumps(ps.ps())


if __name__ == "__main__":
    mainloop = GLib.MainLoop()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    system_bus = dbus.SystemBus()
    name = dbus.service.BusName("org.atomic", system_bus)
    atomic_dbus(system_bus, "/org/atomic/object")
    slip.dbus.service.set_mainloop(mainloop)
    mainloop.run()
