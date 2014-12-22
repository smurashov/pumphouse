import subprocess
import json

import testresources
import testtools


class PHtests(testtools.TestCase, testtools.testcase.WithAttributes,
              testresources.ResourcedTestCase):

    @classmethod
    def setUpClass(cls):
        super(PHtests, cls).setUpClass()
        setup = subprocess.Popen("pumphouse ./api-config.yaml setup"
                                 " --num-tenants 1 --num-servers 1 "
                                 "--num-volumes 1",
                                 shell=True, stdout=subprocess.PIPE)

        if setup.wait() != 0:
            raise Exception("Exit code is incorrect")

    @classmethod
    def tearDownClass(cls):
        super(PHtests, cls).tearDownClass()
        cleanup = subprocess.Popen(["pumphouse", "api-config.yaml",
                                    "cleanup", "source"],
                                   stdout=subprocess.PIPE)

        if cleanup.wait() != 0:
            raise Exception("Exit code is incorrect")

    def tearDown(self):

        super(PHtests, self).tearDown()
        cleanup = subprocess.Popen(["pumphouse", "api-config.yaml",
                                    "cleanup", "destination"],
                                   stdout=subprocess.PIPE)

        if cleanup.wait() != 0:
            raise Exception("Exit code is incorrect")

    def test_image_migrate(self):
        source_resources = subprocess.Popen(["pumphouse", "api-config.yaml",
                                             "get_resources", "source"],
                                            stdout=subprocess.PIPE)

        self.assertEqual(0, source_resources.wait())

        result = json.loads(source_resources.communicate()[0])
        image = next(
            i for i in result["resources"]
            if i["type"] == "image" and "pumphouse" in i["data"]["name"]
        )

        migration = subprocess.Popen("pumphouse ./api-config.yaml migrate "
                                     "images --ids %s" % image["id"],
                                     shell=True, stdout=subprocess.PIPE)

        self.assertEqual(0, migration.wait())

        destination_resources = subprocess.Popen(["pumphouse",
                                                  "api-config.yaml",
                                                  "get_resources",
                                                  "destination"],
                                                 stdout=subprocess.PIPE)

        self.assertEqual(0, destination_resources.wait())

        result = json.loads(destination_resources.communicate()[0])

        self.assertIn(
            image["data"]["name"],
            [i["data"]["name"] for i in result["resources"]
             if i["type"] == "image"]
        )

    def test_identity_migrate(self):
        source_resources = subprocess.Popen(["pumphouse", "api-config.yaml",
                                             "get_resources", "source"],
                                            stdout=subprocess.PIPE)

        self.assertEqual(0, source_resources.wait())

        result = json.loads(source_resources.communicate()[0])
        tenant = next(
            i for i in result["resources"]
            if i["type"] == "tenant" and "pumphouse" in i["data"]["name"]
        )

        migration = subprocess.Popen("pumphouse ./api-config.yaml migrate "
                                     "identity --ids %s" % tenant["id"],
                                     shell=True, stdout=subprocess.PIPE)

        self.assertEqual(0, migration.wait())

        destination_resources = subprocess.Popen(["pumphouse",
                                                  "api-config.yaml",
                                                  "get_resources",
                                                  "destination"],
                                                 stdout=subprocess.PIPE)

        self.assertEqual(0, destination_resources.wait())

        result = json.loads(destination_resources.communicate()[0])

        self.assertIn(
            tenant["data"]["name"],
            [i["data"]["name"] for i in result["resources"]
             if i["type"] == "tenant"]
        )

    def test_server_migrate(self):
        source_resources = subprocess.Popen(["pumphouse", "api-config.yaml",
                                             "get_resources", "source"],
                                            stdout=subprocess.PIPE)

        self.assertEqual(0, source_resources.wait())

        result = json.loads(source_resources.communicate()[0])
        server = next(
            i for i in result["resources"]
            if i["type"] == "server" and "pumphouse" in i["data"]["name"]
        )
        migration = subprocess.Popen("pumphouse ./api-config.yaml migrate "
                                     "servers --ids %s" % server["id"],
                                     shell=True, stdout=subprocess.PIPE)

        self.assertEqual(0, migration.wait())

        destination_resources = subprocess.Popen(["pumphouse",
                                                  "api-config.yaml",
                                                  "get_resources",
                                                  "destination"],
                                                 stdout=subprocess.PIPE)

        self.assertEqual(0, destination_resources.wait())

        result = json.loads(destination_resources.communicate()[0])

        self.assertIn(
            server["data"]["name"],
            [i["data"]["name"] for i in result["resources"]
             if i["type"] == "server"]
        )
        source_resources = subprocess.Popen(["pumphouse", "api-config.yaml",
                                             "get_resources", "source"],
                                            stdout=subprocess.PIPE)

        self.assertEqual(0, source_resources.wait())

        result = json.loads(source_resources.communicate()[0])

        self.assertNotIn(
            server["data"]["name"],
            [i["data"]["name"] for i in result["resources"]
             if i["type"] == "server"]
        )
