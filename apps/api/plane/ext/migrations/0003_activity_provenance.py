import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0122_alter_draftissue_assignees_alter_issue_assignees_and_more'),
        ('squadron_ext', '0002_custom_properties'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityProvenance',
            fields=[
                ('activity', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='squadron_provenance', serialize=False, to='db.issueactivity')),
                ('channel', models.CharField(choices=[('api', 'Api'), ('app', 'App')], max_length=8)),
                ('client_session', models.CharField(blank=True, default='', max_length=255)),
                ('client_agent', models.CharField(blank=True, default='', max_length=255)),
                ('api_token', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='db.apitoken')),
            ],
            options={
                'db_table': 'squadron_ext_activity_provenance',
            },
        ),
    ]
