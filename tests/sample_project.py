from app.schema import Entity, Link, ProjectData


def demo_project() -> ProjectData:
    e = [
        Entity(id="project:atlas", kind="Project", name="Atlas", status="active", description="A collaborative analytics platform for product teams."),
        Entity(id="milestone:launch", kind="Milestone", name="Public beta launch", status="at risk", description="Target release: 24 October 2026"),
        Entity(id="task:auth", kind="Task", name="Ship SSO authentication", status="blocked", owner="Maya Chen", description="Required for the public beta security review."),
        Entity(id="task:security", kind="Task", name="Complete security review", status="in progress", owner="Arjun Rao", description="Waiting on evidence for token rotation and audit logs."),
        Entity(id="task:audit", kind="Task", name="Add audit log coverage", status="in progress", owner="Arjun Rao", description="Audit events for login and permission changes."),
        Entity(id="task:billing", kind="Task", name="Finalize billing webhooks", status="done", owner="Lena Ortiz"),
        Entity(id="pr:184", kind="PullRequest", name="SSO callback and session refresh", status="review requested", owner="Maya Chen", description="Pull request #184 changes the auth service."),
        Entity(id="pr:197", kind="PullRequest", name="Audit event pipeline", status="open", owner="Arjun Rao", description="Pull request #197 adds event writes."),
        Entity(id="service:auth", kind="Service", name="Auth service", status="active"),
        Entity(id="service:gateway", kind="Service", name="API gateway", status="active"),
        Entity(id="person:maya", kind="Person", name="Maya Chen", status="available"),
        Entity(id="person:arjun", kind="Person", name="Arjun Rao", status="available"),
        Entity(id="person:lena", kind="Person", name="Lena Ortiz", status="available"),
        Entity(id="team:platform", kind="Team", name="Platform team"),
        Entity(id="decision:77", kind="Decision", name="Require SSO before public beta", status="approved", description="Security and enterprise onboarding require SSO in the initial release."),
        Entity(id="doc:security", kind="Document", name="Beta launch security checklist", description="SSO, audit logs, token rotation, and access review must pass before release."),
        Entity(id="incident:14", kind="Investigation", name="September auth release delay", status="resolved", description="An earlier SSO delay was resolved by parallelizing callback review and audit validation."),
    ]
    l = [
        Link(source="milestone:launch", target="project:atlas", kind="BELONGS_TO"),
        Link(source="task:auth", target="milestone:launch", kind="REQUIRED_FOR"),
        Link(source="task:security", target="milestone:launch", kind="REQUIRED_FOR"),
        Link(source="task:audit", target="task:security", kind="BLOCKS"),
        Link(source="task:security", target="task:auth", kind="BLOCKS"),
        Link(source="pr:184", target="task:auth", kind="IMPLEMENTS"),
        Link(source="pr:197", target="task:audit", kind="IMPLEMENTS"),
        Link(source="pr:184", target="service:auth", kind="CHANGES"),
        Link(source="service:gateway", target="service:auth", kind="DEPENDS_ON"),
        Link(source="person:maya", target="task:auth", kind="OWNS"),
        Link(source="person:arjun", target="task:security", kind="OWNS"),
        Link(source="person:arjun", target="task:audit", kind="OWNS"),
        Link(source="person:lena", target="task:billing", kind="OWNS"),
        Link(source="person:maya", target="team:platform", kind="MEMBER_OF"),
        Link(source="person:arjun", target="team:platform", kind="MEMBER_OF"),
        Link(source="decision:77", target="task:auth", kind="REQUIRES"),
        Link(source="doc:security", target="decision:77", kind="SUPPORTS"),
        Link(source="incident:14", target="task:auth", kind="ABOUT"),
    ]
    return ProjectData(project_id="atlas", name="Atlas", description="Product analytics platform", entities=e, links=l)
