from rest_framework import serializers

from .models import Organization, Person


class OrganizationSerializer(serializers.ModelSerializer):
    parent_organization_id = serializers.UUIDField(source="parent.organization_id", read_only=True, allow_null=True)

    class Meta:
        model = Organization
        fields = ("organization_id", "name", "code", "parent_organization_id", "is_active")


class PersonSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = Person
        fields = (
            "person_id",
            "employee_id",
            "name",
            "email",
            "organization",
            "organization_name",
            "job_role",
            "employment_status",
            "timezone",
            "fte",
        )
