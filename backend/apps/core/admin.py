from django.contrib import admin
from .models import Workspace, WorkspaceMembership, Vendor, Contract

admin.site.register(Workspace)
admin.site.register(WorkspaceMembership)
admin.site.register(Vendor)
admin.site.register(Contract)
