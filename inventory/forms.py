from django import forms
from .models import Product, Sale, Category, Supplier
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'item_no', 'name', 'category', 'supplier',
            'stock_location', 'unit_price', 'stock_quantity',
            'reorder_level',
            'date_of_last_restocking'
        ]
        widgets = {
            'date_of_last_restocking': forms.DateInput(attrs={'type': 'date'}),
            'unit_price': forms.NumberInput(attrs={'min': 0, 'step': '0.01'}), 
            'stock_quantity': forms.NumberInput(attrs={'min': 0}),
            'reorder_level': forms.NumberInput(attrs={'min': 0}),
}

class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['product', 'quantity_sold', 'sale_price']
        widgets = {
            'product': forms.Select(attrs={'autofocus': True}),  
            'quantity_sold': forms.NumberInput(attrs={'min': 1}), 
            'sale_price': forms.NumberInput(attrs={'min': 0, 'step': '0.01'}),
        }

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

