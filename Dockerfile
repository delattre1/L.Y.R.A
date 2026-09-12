# Lyra, built on the Plow hermes base.
#
# Three things land in three different ways, because the base treats them
# differently and the difference decides what a rebuild picks up.
#
#   SOUL.md   seeded into the home volume on FIRST boot only, by seed_one in
#             stage2-hook.sh. Editing it needs `docker compose down -v`.
#   skills/   synced out of the image into the home on EVERY boot, so a rebuild
#             is enough.
#   scripts/  the base has no mechanism for these, so they live outside the
#             volume and a cont-init.d drops them into place on every boot. A
#             rebuild is enough, which is what you want for code.
#
# The base image reference is the one thing here that is not verified. Take it
# from the plow-hermes-agent README and pass it in, or edit the default:
#   docker compose build --build-arg BASE_IMAGE=<the published base>
# If the pull 403s on stale credentials, `docker logout public.ecr.aws` first.
ARG BASE_IMAGE=public.ecr.aws/plow/plow-hermes-agent:SET-THIS-FROM-THE-BASE-README
FROM ${BASE_IMAGE}

# Readable by the hermes user, because stage2-hook copies it as that user.
COPY --chmod=0644 SOUL.md /opt/hermes/docker/SOUL.md

# skills_sync.py reads this tree on every container start.
COPY --chmod=0644 skills/ /opt/hermes/skills/

# The checks themselves. SKILL.md calls them by absolute path under the home,
# and 03-lyra-scripts is what puts them there.
COPY --chmod=0755 scripts/ /opt/lyra/scripts/
COPY --chmod=0755 tests/ /opt/lyra/tests/

# Feed downloads and the domain age cache belong on the volume, so a restart
# does not go back to the sources for a copy we already have.
ENV LYRA_STATE=/var/lib/hermes/lyra

# The leaderboard reporter's client, pinned to the commit the plow-agents README
# names. Registering is a one-off you run from the host; see the README.
ADD --chmod=0644 https://raw.githubusercontent.com/plow-pbc/agent-index-client/f900ff144076f0a766584b6ec4d0993600779b16/standalone/agent_index_client.py /opt/lyra/agent_index_client.py

COPY --chmod=0755 image/cont-init.d/ /etc/cont-init.d/
COPY image/s6-overlay/s6-rc.d/ /etc/s6-overlay/s6-rc.d/
# Named rather than globbed: a glob here would also restat the base's own
# services, and would go through silently if one of ours failed to copy.
RUN chmod 0755 /etc/s6-overlay/s6-rc.d/feed-refresh/run \
               /etc/s6-overlay/s6-rc.d/agent-index/run \
               /etc/s6-overlay/s6-rc.d/agent-index/finish
