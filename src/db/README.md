# Talus Database

Mongodb has been chosen as the database for Talus

# Watching for changes

Monitoring mongodb for changes will be an integral part of
Talus. This will be done using replica sets, which logs all
actions to an operations log (oplog).

See http://stackoverflow.com/questions/9691316/how-to-listen-for-changes-to-a-mongodb-collection
for more details.


