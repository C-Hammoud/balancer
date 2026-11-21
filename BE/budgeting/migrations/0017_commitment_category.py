from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('budgeting', '0016_savings_currency'),
    ]

    operations = [
        migrations.AddField(
            model_name='commitment',
            name='category_id',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
