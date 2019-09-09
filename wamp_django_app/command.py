import datetime

from django.apps import apps
from django.db import transaction
from django.core.management.base import BaseCommand as DjangoBaseCommand

from wampbaseapp.wamp_app import WampApp as WampBaseApp, register_method


class WampApp(WampBaseApp):
    PRINCIPAL = 'PRINCIPAL'
    models = {}
    apps = {}

    @classmethod
    def get_app_config(cls, app_name):
        try:
            return cls.apps[app_name]
        except KeyError:
            app_config = apps.get_app_config(app_name)
            cls.apps[app_name] = app_config
            return app_config

    @classmethod
    def load_model(cls, model_path):
        app_name, model_name = model_path.split(':')
        app = cls.get_app_config(app_name)
        return app.get_model(model_name)

    @classmethod
    def get_model(cls, model_path):
        try:
            return cls.models[model_path]
        except KeyError:
            model = cls.load_model(model_path)
            cls.models[model_path] = model
            return model

    def post_init(self):
        new_methods_map = {}

        def decorate(method):
            async def new_method(model_path, *args, **kwargs):

                def sync_method(model_path, *args, **kwargs):
                    model = self.get_model(model_path)
                    return method(model, *args, **kwargs)

                return await self.async_run(sync_method, model_path, *args, **kwargs)

            return new_method

        for method_name, method_data in self.methods.items():
            method, options = method_data
            new_method = decorate(method)
            new_methods_map[method_name] = (new_method, options)
        self.methods = new_methods_map

    @register_method('get')
    def get(self, model, search_params):
        obj = model.objects.get(**search_params)
        return obj.serialize()

    @register_method('filter')
    def filter(self, model, search_params):
        objects = model.objects.filter(**search_params)
        return [obj.serialize() for obj in objects]

    @register_method('get_or_create')
    def get_or_create(self, model, data, defaults={}):
        obj, created = model.objects.get_or_create(**data, defaults=defaults)
        return obj.serialize(), created

    @register_method('create')
    def create(self, model, data):
        obj = model.objects.create(**data)
        return obj.serialize()

    @register_method('get_or_insert')
    def get_or_insert(self, model, data):
        obj, created = model.objects.get_or_insert(**data)
        return obj.serialize(), created

    @register_method('update_or_create')
    def update_or_create(self, model, data, defaults={}):
        obj, created = model.objects.update_or_create(**data, defaults=defaults)
        return obj.serialize(), created

    @register_method('delete')
    def delete(self, model, search_params):
        return model.objects.filter(**search_params).delete()

    @register_method('multi_insert')
    def multi_insert(self, model, rows):
        counter = 0
        with transaction.atomic():
            for data in rows:
                model.objects.create(**data)
                counter += 1
        return counter

    @register_method('multi_put')
    def multi_put(self, model, rows):
        counter = 0
        with transaction.atomic():
            for data in rows:
                model.objects.get_or_create(id=data['id'], defaults=data)
                counter += 1
        return counter

    @register_method('update')
    def update(self, model, search_params, data):
        field_names = tuple(f.name for f in model._meta.fields)
        if 'updated_at' in field_names:
            data['updated_at'] = datetime.datetime.now()
        queryset = model.objects.filter(**search_params)
        queryset.update(**data)
        return queryset.count()


class Command(DjangoBaseCommand, WampApp):
    PRINCIPAL = 'PRINCIPAL'
    METHODS_PREFIX = ''
    METHODS_SUFFIX = ''

    def wamp_run(self):
        WampApp.PRINCIPAL = self.PRINCIPAL
        WampApp.METHODS_PREFIX = self.METHODS_PREFIX
        WampApp.METHODS_SUFFIX = self.METHODS_SUFFIX

        WampApp.run()

    def handle(self, *args, **kwargs):
        self.wamp_run()
