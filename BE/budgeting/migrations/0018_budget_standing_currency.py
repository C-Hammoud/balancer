from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('budgeting', '0017_commitment_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='budget',
            name='currency',
            field=models.CharField(blank=True, default='', max_length=3),
        ),
        migrations.AddField(
            model_name='financialstanding',
            name='currency',
            field=models.CharField(blank=True, default='', max_length=3),
        ),
    ]
