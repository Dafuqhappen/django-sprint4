from django.contrib import admin

from .models import Post, Category, Location


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'description',
        'slug'
    )

    list_filter = (
        'title',
        'slug'
    )

    empty_value_display = 'Не задано'


admin.site.register(Location)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'text',
        'pub_date',
        'author',
        'location',
        'category'
    )
    list_filter = (
        'pub_date',
        'author',
        'location',
        'category'
    )
    search_fields = (
        'title',
        'text'
    )

    empty_value_display = 'Не задано'
