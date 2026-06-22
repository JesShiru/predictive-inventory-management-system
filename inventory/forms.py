from django import forms
from .models import Product, Sale
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'item_no', 'name', 'category', 
            'stock_location', 'unit_price', 'stock_quantity',
            'reorder_level',
            'date_of_last_restocking',
            'expiry_date',
        ]
        widgets = {
            'date_of_last_restocking': forms.DateInput(attrs={'type': 'date'}),
            'unit_price': forms.NumberInput(attrs={'min': 0, 'step': '0.01'}), 
            'stock_quantity': forms.NumberInput(attrs={'min': 0}),
            'reorder_level': forms.NumberInput(attrs={'min': 0}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        stock_qty = cleaned_data.get('stock_quantity')
        reorder_level = cleaned_data.get('reorder_level')
        expiry_date = cleaned_data.get('expiry_date')
        
        from datetime import date

        # Reorder level cannot exceed current stock
        if reorder_level is not None and stock_qty is not None:
            if reorder_level > stock_qty:
                self.add_error(
                    'reorder_level',
                    f'Reorder level ({reorder_level}) cannot exceed stock quantity ({stock_qty}).'
                )

        # Expiry date must be in the future
        if expiry_date and expiry_date < date.today():
            self.add_error('expiry_date', 'Expiry date cannot be in the past.')

        return cleaned_data

class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['product', 'quantity_sold', 'sale_price']
        widgets = {
            'product': forms.Select(attrs={'autofocus': True}),  
            'quantity_sold': forms.NumberInput(attrs={'min': 1}), 
            'sale_price': forms.NumberInput(attrs={'min': 0, 'step': '0.01'}),
        }


class AdminUserCreationForm(UserCreationForm):
    """
    Admin-only form for creating system users.
    Allows admins to assign staff roles and set email.
    """
    email = forms.EmailField(required=True, help_text="User's contact email")
    is_staff = forms.BooleanField(
        required=False,
        help_text="Designates whether the user can access the admin panel."
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'is_staff']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_staff = self.cleaned_data.get('is_staff', False)
        if commit:
            user.save()
        return user

