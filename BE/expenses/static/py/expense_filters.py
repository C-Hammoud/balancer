from django import template

register = template.Library()

@register.filter
def consumption_type_display(value):
    types = {
        'market': 'Market',
        'transport':'Transport', 
        'food': 'Food',
        'other': 'Other',
    }
    return types.get(value, value.capitalize())