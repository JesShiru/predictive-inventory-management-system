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


class AdminUserCreationForm(UserCreationForm):
    """
    Admin-only form for creating system users.
    Allows admins to assign staff/superuser roles and set email.
    """
    email = forms.EmailField(required=True, help_text="User's contact email")
    is_staff = forms.BooleanField(
        required=False,
        help_text="Designates whether the user can access the admin panel."
    )
    is_superuser = forms.BooleanField(
        required=False,
        help_text="Designates whether the user has all permissions (superuser)."
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'is_staff', 'is_superuser']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_staff = self.cleaned_data.get('is_staff', False)
        user.is_superuser = self.cleaned_data.get('is_superuser', False)
        if commit:
            user.save()
        return user

