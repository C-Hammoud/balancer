from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('budgeting', '0015_plan_sub_budgets'),
    ]

    operations = [
        migrations.AddField(
            model_name='savings',
            name='currency',
            field=models.CharField(blank=True, default='', max_length=3),
        ),
    ]
