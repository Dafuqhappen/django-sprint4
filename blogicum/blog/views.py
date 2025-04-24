from django.utils import timezone
from django.db.models import Count
from django.urls import reverse, reverse_lazy
from django.http import Http404
from django.views.generic import (
    CreateView, DetailView, DeleteView, ListView, UpdateView
)
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404

from .models import Post, Category, Comment, User
from .forms import PostForm, ProfileEditForm, CommentForm

POSTS_LIMIT = 10


def index(request):
    """
    Главная страница блога.
    Отображаются последние опубликованные посты с пагинацией
    (не более 10 записей на страницу).
    """
    queryset = get_posts_queryset(with_filters=True, with_annotations=True)
    paginator = Paginator(queryset, POSTS_LIMIT)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'blog/index.html', {'page_obj': page_obj})


def get_posts_queryset(with_filters=False, with_annotations=False):
    """
    Возвращает базовый QuerySet для модели Post с опциональной фильтрацией
    и аннотацией.
    """
    qs = Post.objects.select_related('author', 'category', 'location')
    if with_filters:
        qs = qs.filter(
            is_published=True,
            pub_date__lte=timezone.now(),
            category__is_published=True
        )
    if with_annotations:
        qs = qs.annotate(
            comment_count=Count('comments')
        ).order_by(*Post._meta.ordering)
    return qs


class ProfileListView(ListView):
    """
    Страница профиля пользователя.
    Если залогиненный пользователь просматривает свой профиль,
    отображаются все его посты.
    Иначе — только опубликованные посты.
    """

    template_name = 'blog/profile.html'
    context_object_name = 'post_list'
    paginate_by = POSTS_LIMIT

    def get_profile_user(self):
        return get_object_or_404(User, username=self.kwargs.get('username'))

    def get_queryset(self):
        user_obj = self.get_profile_user()
        if self.request.user == user_obj:
            qs = get_posts_queryset(with_annotations=True)
        else:
            qs = get_posts_queryset(with_filters=True, with_annotations=True)
        return qs.filter(author=user_obj)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile'] = self.get_profile_user()
        return context


class CategoryListView(ListView):
    """
    Страница категории.
    Отображаются посты указанной категории (параметр URL: category_slug),
    удовлетворяющие условиям публикации.
    В контекст добавляется информация о категории.
    """

    template_name = 'blog/category.html'
    paginate_by = POSTS_LIMIT
    context_object_name = 'post_list'

    def get_category(self):
        return get_object_or_404(
            Category,
            slug=self.kwargs.get('category_slug'),
            is_published=True
        )

    def get_queryset(self):
        category = self.get_category()
        return get_posts_queryset(
            with_filters=True, with_annotations=True
        ).filter(category=category)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.get_category()
        return context


class PostDetailView(DetailView):
    """
    Детальная страница поста.
    """

    model = Post
    template_name = 'blog/detail.html'
    context_object_name = 'post'
    pk_url_kwarg = 'post_id'

    def get_object(self, queryset=None):
        post = super().get_object(queryset)
        if self.request.user != post.author and not (
            post.is_published and
            post.pub_date <= timezone.now() and
            post.category.is_published
        ):
            raise Http404("Пост не найден")
        return post

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = CommentForm()
        context['comments'] = (
            self.object.comments.
            select_related('author')
            .order_by('created_at')
        )
        return context


class PostCreateView(LoginRequiredMixin, CreateView):
    """
    Страница создания нового поста.
    Доступна только авторизованным пользователям.
    Использует форму PostForm
    При успешной отправке записи перенаправляет пользователя на его страницу.
    """

    model = Post
    form_class = PostForm
    template_name = 'blog/create.html'

    def form_valid(self, form):
        post = form.save(commit=False)
        post.author = self.request.user
        post.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "blog:profile", kwargs={
                "username": self.request.user.username})


class PostUpdateView(LoginRequiredMixin, UpdateView):
    """
    Страница редактирования поста.
    Доступна только автору поста.
    Если текущий пользователь не является автором,
    происходит перенаправление на детальную страницу поста.
    Использует тот же шаблон, что и PostCreateView.
    После редактирования перенаправляет на страницу отредактированного поста.
    """

    model = Post
    form_class = PostForm
    template_name = 'blog/create.html'
    context_object_name = 'post'
    pk_url_kwarg = 'post_id'

    def dispatch(self, request, *args, **kwargs):
        post = get_object_or_404(Post, pk=kwargs.get('post_id'))
        if post.author != request.user:
            return redirect('blog:post_detail', post_id=kwargs.get('post_id'))
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy(
            'blog:post_detail',
            kwargs={'post_id': self.kwargs.get('post_id')}
        )


class PostDeleteView(LoginRequiredMixin, DeleteView):
    """
    Страница удаления поста.
    Доступна только для автора поста или администратора.
    Перед удалением открывается подтверждающая страница.
    После успешного удаления происходит перенаправление на страницу профиля.
    """

    model = Post
    template_name = "blog/comment.html"
    context_object_name = "post"
    pk_url_kwarg = 'post_id'   # без этой строчки тесты падают
                               # (Generic detail view must be called 
                               # with either an object pk or a slug.)

    def dispatch(self, request, *args, **kwargs):
        post = self.get_object()
        if post.author != request.user and not request.user.is_staff:
            return redirect("blog:post_detail", post_id=post.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy(
            "blog:profile", kwargs={
                "username": self.request.user.username})


class CommentCreateView(LoginRequiredMixin, CreateView):
    """
    Страница добавления комментария к посту.
    Доступна только авторизованным пользователям.
    При успешном добавлении комментария происходит перенаправление на
    детальную страницу поста.
    """

    model = Comment
    form_class = CommentForm
    template_name = "blog/comment.html"

    def form_valid(self, form):
        post = get_object_or_404(Post, pk=self.kwargs.get('post_id'))
        form.instance.author = self.request.user
        form.instance.post = post
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            'blog:post_detail',
            kwargs={'post_id': self.kwargs.get('post_id')}
        )


class CommentUpdateView(LoginRequiredMixin, UpdateView):
    """
    Страница редактирования комментария.
    Доступна только автору комментария.
    После сохранения изменений происходит перенаправление на страницу поста.
    """

    model = Comment
    form_class = CommentForm
    template_name = "blog/comment.html"
    context_object_name = "comment"

    def dispatch(self, request, *args, **kwargs):
        comment = get_object_or_404(
            Comment,
            pk=kwargs.get('comment_id'),
            post__pk=kwargs.get('post_id')
        )
        if comment.author != request.user:
            return redirect('blog:post_detail', post_id=kwargs.get('post_id'))
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return get_object_or_404(
            Comment,
            pk=self.kwargs.get('comment_id'),
            post__pk=self.kwargs.get('post_id')
        )

    def get_success_url(self):
        return reverse_lazy(
            'blog:post_detail',
            kwargs={'post_id': self.kwargs.get('post_id')}
        )


class CommentDeleteView(LoginRequiredMixin, DeleteView):
    """
    Страница удаления комментария.
    Доступна только для автора комментария.
    Перед удалением отображается подтверждающая страница.
    После удаления происходит перенаправление на страницу поста.
    """

    model = Comment
    template_name = "blog/comment.html"
    context_object_name = "comment"

    def dispatch(self, request, *args, **kwargs):
        comment = self.get_object()
        if comment.author != self.request.user:
            return redirect("blog:post_detail", post_id=comment.post.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return get_object_or_404(
            Comment,
            pk=self.kwargs.get('comment_id'),
            post__pk=self.kwargs.get('post_id')
        )

    def get_success_url(self):
        return reverse_lazy(
            "blog:post_detail", kwargs={ 
                "post_id": self.object.post.pk}
        ) 


@login_required
def edit_profile(request):
    """
    Функция редактирования профиля пользователя.
    Предоставляет форму для изменения личных данных
    (имя, фамилия, email, логин).
    При корректном заполнении данные сохраняются,
    и пользователь перенаправляется на свою страницу профиля.
    """
    user_obj = request.user
    form = ProfileEditForm(request.POST or None, instance=user_obj)
    if form.is_valid():
        form.save()
        return redirect("blog:profile", username=user_obj.username)
    return render(request, "blog/user.html",
                  {"form": form, "profile": user_obj})
