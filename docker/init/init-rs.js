// docker/init/init-rs.js
// Inicializa el replica set asegurando que no se duplique la configuración

const replConfig = {
  _id: "my-replicaset",
  members: [
    { _id: 0, host: "mongo1:30001", priority: 2 },
    { _id: 1, host: "mongo2:30002", priority: 1 },
    { _id: 2, host: "mongo3:30003", priority: 1 },
  ],
};

function initiateReplicaSet() {
  const status = rs.status();

  if (status.ok === 1 && status.members && status.members.length > 0) {
    print("Replica set already configured. Current status:");
    printjson(status);
    return;
  }

  try {
    rs.initiate(replConfig);
    print("Replica set initiated correctly.");
  } catch (error) {
    print("Error initiating replica set:", error);
  }
}

function waitForPrimary(maxRetries = 20) {
  let retries = 0;
  while (retries < maxRetries) {
    const status = rs.status();
    const primary = status.members?.find((member) => member.stateStr === "PRIMARY");
    if (primary) {
      print("Replica set PRIMARY is ready:", primary.name);
      return;
    }
    print("Waiting for PRIMARY election...");
    sleep(2000);
    retries += 1;
  }
  print("PRIMARY was not elected within the expected time.");
}

initiateReplicaSet();
sleep(3000);
waitForPrimary();

