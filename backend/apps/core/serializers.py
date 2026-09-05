from rest_framework import serializers
from .models import Workspace, Vendor, Contract


class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ["id", "name", "slug", "settings_json", "created_at"]


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = [
            "id", "workspace", "name", "contacts", "payment_terms_days",
            "risk_score", "risk_factors", "risk_explanation", "risk_updated_at",
            "created_at",
        ]
        read_only_fields = ["risk_score", "risk_factors", "risk_explanation", "risk_updated_at"]


class ContractSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id", "workspace", "vendor", "vendor_name", "file", "terms",
            "valid_from", "valid_until", "status", "created_at",
        ]
