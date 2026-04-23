FROM m.daocloud.io/docker.elastic.co/elasticsearch/elasticsearch:8.11.0

RUN /usr/share/elasticsearch/bin/elasticsearch-plugin install --batch \
    https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-8.11.0.zip
