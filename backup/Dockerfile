FROM postgres:16

RUN apt-get update \
 && apt-get install -y --no-install-recommends gnupg jq ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY backup.sh /usr/local/bin/backup.sh
RUN sed -i 's/\r$//' /usr/local/bin/backup.sh && chmod 0755 /usr/local/bin/backup.sh

ENTRYPOINT ["/bin/bash", "/usr/local/bin/backup.sh"]
