from django.db import models

class SAMLConfiguration(models.Model):
    project = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=256)

    def __str__(self):
        return "SAML config for {}".format(self.project)
