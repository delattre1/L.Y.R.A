# Lyra, built on the Plow hermes base.
#
# Pinned to an immutable tag, as the base asks. There is no `latest`: one tag per
# commit of plow-hermes-agent, `base-` plus the full 40-character SHA. To move
# it, list what is published and take the newest that your checkout also has:
#
#   token=$(curl -fsSL 'https://public.ecr.aws/token/?service=public.ecr.aws&scope=repository:e1h7x4a2/plow-cloud-agents:pull' \
#     | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
#   curl -fsSL -H "Authorization: Bearer $token" \
#     https://public.ecr.aws/v2/e1h7x4a2/plow-cloud-agents/tags/list
#
# A 403 on pull is stale registry credentials, not the tag: docker logout
# public.ecr.aws, then build again.
ARG BASE_IMAGE=public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-51f83158a70a383f03a4d03dbd8b6ea102cf0361@sha256:253d7ed3409effa7fa59113d93b4b79bb731d8264cdaf4cd60294924d0110a2e
FROM ${BASE_IMAGE}

# No COPY --chmod anywhere in this file. It is BuildKit-only, and a stock Docker
# still selects the legacy builder, where it fails the build outright. The base
# says so and does the mode in its own step; so do we.

# Identity. plow-init composes the home's SOUL.md on every boot as the base
# persona followed by this file, so this is an addition to a persona rather than
# a whole one, and nothing here writes /var/lib/hermes/SOUL.md directly: that
# path is overwritten at boot.
COPY --chown=0:0 SOUL.md /opt/hermes/plow-seed/persona.md
RUN chmod 0644 /opt/hermes/plow-seed/persona.md

# Both copies, as the base image does with its own. The second is what a home
# that starts empty is seeded from and what later image updates reach; it is a
# source and not a backup, so a skill the agent deleted stays deleted.
COPY --chown=10000:10000 skills/ /var/lib/hermes/skills/
COPY --chown=10000:10000 skills/ /opt/hermes/skills/

# The checks. SKILL.md calls them by absolute path under the home, and
# 03-lyra-scripts is what puts them there on every boot, which is the behaviour
# code wants: a rebuild reaches them without destroying the agent's sessions.
COPY --chown=0:0 image/status_phrases.yaml /opt/lyra/status_phrases.yaml
COPY --chown=0:0 scripts/ /opt/lyra/scripts/
COPY --chown=0:0 tests/ /opt/lyra/tests/

# The leaderboard reporter's client, pinned by commit AND checksum: a commit URL
# alone trusts whatever GitHub serves. Checked in a RUN, not ADD --checksum,
# which is BuildKit-only like COPY --chmod. The reporter registers on its own.
ADD https://raw.githubusercontent.com/plow-pbc/agent-index-client/3f116994930cb3d1c23a485851953dd6c1eef039/standalone/agent_index_client.py /opt/lyra/agent_index_client.py
RUN echo "b23e7db974b1bd00b50557b44d759df170fc6ef17b471c9cfc0cd975843b535c  /opt/lyra/agent_index_client.py" | sha256sum -c -

COPY --chown=0:0 image/cont-init.d/ /etc/cont-init.d/
COPY --chown=0:0 image/s6-overlay/s6-rc.d/ /etc/s6-overlay/s6-rc.d/

# Modes in their own step, and named rather than globbed: a glob would also
# restat the base's own services and would pass silently if one of ours failed
# to copy.
RUN chmod -R 0755 /opt/lyra/scripts /opt/lyra/tests \
 && chmod 0644 /opt/lyra/agent_index_client.py \
 && chmod 0755 /etc/cont-init.d/03-lyra-scripts \
                /etc/s6-overlay/s6-rc.d/feed-refresh/run \
                /etc/s6-overlay/s6-rc.d/agent-index/run \
                /etc/s6-overlay/s6-rc.d/agent-index/finish

# Feed downloads and the domain age cache belong on the volume, so a restart
# does not go back to the sources for a copy we already have.
ENV LYRA_STATE=/var/lib/hermes/lyra
