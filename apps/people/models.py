import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(TimeStampedModel):
    organization_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ResponsibilityLevel(TimeStampedModel):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    rank_order = models.PositiveIntegerField()

    class Meta:
        ordering = ["rank_order"]

    def __str__(self) -> str:
        return self.name


class Person(TimeStampedModel):
    person_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="people")
    manager = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="direct_reports")
    responsibility_level = models.ForeignKey(ResponsibilityLevel, null=True, blank=True, on_delete=models.PROTECT)
    job_role = models.CharField(max_length=100)
    employment_status = models.CharField(max_length=30, default="ACTIVE")
    timezone = models.CharField(max_length=50, default="Asia/Seoul")
    fte = models.DecimalField(max_digits=3, decimal_places=2, default=1.00)
    data_origin = models.CharField(max_length=30, default="SYNTHETIC")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.employee_id})"


class Skill(TimeStampedModel):
    skill_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class PersonSkill(TimeStampedModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="person_skills")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT)
    proficiency = models.PositiveSmallIntegerField(help_text="1~5")
    confidence = models.DecimalField(max_digits=3, decimal_places=2, default=1.00)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["person", "skill"], name="unique_person_skill")]


class WorkSchedule(TimeStampedModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="work_schedules")
    weekly_hours = models.DecimalField(max_digits=5, decimal_places=2, default=40.00)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)


class PersonAbsence(TimeStampedModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="absences")
    absence_type = models.CharField(max_length=30)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(max_length=30, default="APPROVED")


class IdentityLink(TimeStampedModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="identity_links")
    system_type = models.CharField(max_length=30)
    external_account_id = models.CharField(max_length=255)
    external_email = models.EmailField(blank=True)
    mapping_status = models.CharField(max_length=30, default="PENDING")
    match_method = models.CharField(max_length=30, default="EMAIL")
    confidence = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    manual_override = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["system_type", "external_account_id"], name="unique_external_identity"),
        ]
