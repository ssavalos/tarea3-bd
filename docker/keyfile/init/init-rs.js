// init-rs.js
const cfg = {
  _id: "my-replica-set",
  members: [
    { _id: 0, host: "mongo1:30001", priority: 2 },
    { _id: 1, host: "mongo2:30002", priority: 1 },
    { _id: 2, host: "mongo3:30003", priority: 1 }
  ]
};

try {
  rs.initiate(cfg);
  print("Replica set initiated.");
} catch (e) {
  print("Replica set may already be initiated:", e);
}

// Espera y muestra estado
sleep(5000);
printjson(rs.status());
