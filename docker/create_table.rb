create 'orders',
  { NAME => 'd', VERSIONS => 1 },
  { REGION_REPLICATION => 3, SPLITS => ['2', '4', '6', '8', 'a', 'c', 'e'] }
exit
