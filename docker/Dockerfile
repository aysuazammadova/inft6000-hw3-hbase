# One image for every HDFS and HBase node. The role is chosen by the container command.
FROM eclipse-temurin:11-jre-jammy

ARG HADOOP_VERSION=3.4.3
ARG HBASE_VERSION=2.6.7

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl netcat-openbsd procps \
 && rm -rf /var/lib/apt/lists/*

# Download from the Apache CDN, fall back to the permanent archive.
RUN set -eux; \
    fetch() { curl -fSL "https://dlcdn.apache.org/$1" -o "$2" || curl -fSL "https://archive.apache.org/dist/$1" -o "$2"; }; \
    fetch "hadoop/common/hadoop-${HADOOP_VERSION}/hadoop-${HADOOP_VERSION}.tar.gz" /tmp/hadoop.tgz; \
    fetch "hbase/${HBASE_VERSION}/hbase-${HBASE_VERSION}-hadoop3-bin.tar.gz" /tmp/hbase.tgz; \
    mkdir -p /opt/hadoop /opt/hbase; \
    tar -xzf /tmp/hadoop.tgz -C /opt/hadoop --strip-components=1; \
    tar -xzf /tmp/hbase.tgz -C /opt/hbase --strip-components=1; \
    rm -rf /tmp/*.tgz /opt/hadoop/share/doc /opt/hbase/docs

ENV HADOOP_HOME=/opt/hadoop \
    HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop \
    HBASE_HOME=/opt/hbase \
    HBASE_CONF_DIR=/opt/hbase/conf \
    HBASE_MANAGES_ZK=false \
    HBASE_DISABLE_HADOOP_CLASSPATH_LOOKUP=true \
    PATH=/opt/hbase/bin:/opt/hadoop/bin:$PATH

COPY entrypoint.sh init-table.sh create_table.rb /opt/hw3/
RUN chmod +x /opt/hw3/*.sh

ENTRYPOINT ["/opt/hw3/entrypoint.sh"]
