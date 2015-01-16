#!/usr/bin/env python3

YNAB_DIR = "/Users/farthen/Dropbox/YNAB/"

import json
import os.path
import fnmatch
import datetime
import decimal


class ConfigDir:

    def __init__(self, root_directory):
        self.root_directory = root_directory

    def get_budget(self, name):
        for filename in os.listdir(self.root_directory):
            if fnmatch.fnmatch(filename, name + '*.ynab4'):
                return Budget(os.path.join(self.root_directory, filename))


class Budget:

    def __init__(self, root_directory):
        self.root_directory = root_directory
        self.ymetafile = os.path.join(root_directory, 'Budget.ymeta')
        self.data_directory = self.get_data_path()
        self.budget_filename = os.path.join(
            self.data_directory, 'Budget.yfull')
        self.full_budget = self.get_full_budget()

    def get_data_path(self):
        with open(self.ymetafile, encoding='utf-8') as file:
            data = json.load(file)

        name = data['relativeDataFolderName']
        data1 = os.path.join(self.root_directory, name)

        for filename in os.listdir(data1):
            if fnmatch.fnmatch(filename, '[0-9A-Z]*-*-*-*-*[0-9A-Z]'):
                return os.path.join(data1, filename)

    def get_full_budget(self):
        def parse_decimal(string):
            return decimal.Decimal(string)

        with open(self.budget_filename, encoding='utf-8') as file:
            return FullBudget(json.load(file, parse_float=parse_decimal))


class FullBudget:

    def __init__(self, data):
        self.budgetdict = data
        self.categories = self.get_categories()

        self.sub_category_ids = {}
        for master_cat in self.categories:
            if master_cat.subCategories:
                for sub_cat in master_cat.subCategories:
                    if sub_cat.entityId:
                        self.sub_category_ids[sub_cat.entityId] = sub_cat

        self.sub_category_ids['Category/__ImmediateIncome__'] = SubCategory({
            'entityId': 'Category/__ImmediateIncome__',
            'entityType': 'category',
            'name': 'Special: Immediate Income',
            'type': 'INFLOW',
            'masterCategoryId': None
        }, None)

        self.budgets = self.get_budgets()
        self.transactions = self.get_transactions()

    def get_budget_now(self):
        date = datetime.date.today()
        return self.get_budget_for_year_month(date.year, date.month)

    def get_budget_for_year_month(self, year, month):
        for budget in self.budgets:
            if budget.year == year and budget.month == month:
                return budget

    def get_budgets(self):
        if 'monthlyBudgets' not in self.budgetdict:
            return []

        return [MonthlyBudget(catdict, self) for catdict in self.budgetdict['monthlyBudgets']]

    def get_transactions(self):
        if 'transactions' not in self.budgetdict:
            return []

        return [Transaction(transdict, self) for transdict in self.budgetdict['transactions']]

    def get_transactions_for_year_month(self, year, month):
        return [trans for trans in self.transactions if trans.year == year and trans.month == month]

    def get_transactions_now(self):
        date = datetime.date.today()
        return self.get_transactions_for_year_month(date.year, date.month)

    def get_category_amounts(self, year, month):
        transactions = self.get_transactions_for_year_month(year, month)
        categories = self.get_visible_categories()

        subbuds = self.get_budget_now().sub_category_budgets
        amounts = {}

        for bud in subbuds:
            amounts[bud.category] = bud.amount

        for trans in transactions:
            if trans.category in categories:
                amounts[trans.category] += trans.amount

        return amounts

    def get_category_amounts_now(self):
        date = datetime.date.today()
        return self.get_category_amounts(date.year, date.month)

    def get_category_by_id(self, catid):
        if catid in self.sub_category_ids:
            return self.sub_category_ids[catid]
        return None

    def get_categories(self):
        if 'masterCategories' not in self.budgetdict:
            return []

        return [MasterCategory(catdict) for catdict in self.budgetdict['masterCategories']]

    def get_visible_categories(self):
        visible_cats = []
        for cat in self.get_visible_master_categories():
            for subcat in cat.get_visible_sub_categories():
                visible_cats.append(subcat)

        return visible_cats

    def get_visible_master_categories(self):
        return [cat for cat in self.categories if cat.is_visible()]

    def get_inflow_master_categories(self):
        return [cat for cat in self.get_visible_master_categories() if cat.type == 'INFLOW']

    def get_outflow_master_categories(self):
        return [cat for cat in self.get_visible_master_categories() if cat.type == 'OUTFLOW']


class Entity:

    def __init__(self, data):
        self.edict = data

        self.entityId = None
        if 'entityId' in data:
            self.entityId = data['entityId']

        self.entityType = None
        if 'entityType' in data:
            self.entityType = data['entityType']


class Transaction(Entity):

    def __init__(self, data, full_budget):
        super().__init__(data)

        self.category_id = data['categoryId']

        self.is_transfer = False
        if 'transferTransactionId' in data:
            self.is_transfer = True
            self.transfer_transaction_id = data['transferTransactionId']
            self.category = SubCategory({
                'entityId': 'Category/__Transfer__',
                'entityType': 'category',
                'name': 'Special: Transfer',
                'type': 'TRANSFER',
                'masterCategoryId': None
            }, None)
        else:
            self.category = full_budget.get_category_by_id(self.category_id)
        date_elems = data['date'].split('-')
        self.year = int(date_elems[0])
        self.month = int(date_elems[1])
        self.day = int(date_elems[2])
        self.amount = decimal.Decimal(data['amount'])

    def __repr__(self):
        if self.category is None:
            return "<Transaction category=INVALID>"

        return '<Transaction category="' + str(self.category) + '", date="' + str(self.year) + '-' + str(self.month) + '-' + str(self.day) + '"'


class Category(Entity):

    def __init__(self, data):
        super().__init__(data)

        self.name = None
        if 'name' in data:
            self.name = data['name']

        self.data = None
        if 'type' in data:
            self.type = data['type']

        self.isTombstone = False
        if 'isTombstone' in data:
            self.isTombstone = data['isTombstone']

    def __repr__(self):
        return '<Category name="' + self.name + '">'

    def is_visible(self):
        if self.isTombstone:
            return False

        if self.entityId:
            attr = self.entityId.split('/')
            if len(attr) >= 2 and attr[1] in ('__Hidden__', '__Internal__'):
                return False

        return True


class SubCategory(Category):

    def __init__(self, data, master):
        super().__init__(data)

        self.master = master

    def __repr__(self):
        if not self.master:
            return '<SubCategory name="' + self.name + '">'
        return '<SubCategory name="' + self.name + '", master.name="' + self.master.name + '">'


class MasterCategory(Category):

    def __init__(self, data):
        super().__init__(data)

        self.subCategories = None
        if 'subCategories' in data and data['subCategories'] is not None:
            self.subCategories = [
                SubCategory(cat, self) for cat in data['subCategories']]

    def get_visible_sub_categories(self):
        if self.subCategories is None:
            return []

        return [cat for cat in self.subCategories if cat.is_visible()]

    def __repr__(self):
        return '<MasterCategory name="' + self.name + '">'


class MonthlyBudget:

    def __init__(self, data, full_budget):
        self.data = data
        self.full_budget = full_budget
        self.entityId = data['entityId']

        self.datestr = self.entityId.split('/')[1]
        self.year = int(self.datestr.split('-')[0])
        self.month = int(self.datestr.split('-')[1])

        self.sub_category_budgets = self.get_sub_category_budgets()

    def __repr__(self):
        return '<MonthlyBudget year="' + str(self.year) + '", month="' + str(self.month) + '">'

    def get_sub_category_budgets(self):
        if not 'monthlySubCategoryBudgets' in self.data or self.data['monthlySubCategoryBudgets'] is None:
            return []

        return [MonthlySubCategoryBudget(budget, self) for budget in self.data['monthlySubCategoryBudgets']]


class MonthlySubCategoryBudget:

    def __init__(self, data, monthly_budget):
        self.monthly_budget = monthly_budget
        self.category_id = data['categoryId']
        self.category = self.monthly_budget.full_budget.get_category_by_id(
            self.category_id)
        self.amount = decimal.Decimal(data['budgeted'])

    def __repr__(self):
        if self.category is None:
            return '<MonthlySubCategoryBudget category=INVALID amount="' + str(self.amount) + '">'

        return '<MonthlySubCategoryBudget category="' + self.category.name + '" amount="' + str(self.amount) + '">'

if __name__ == '__main__':
    parser = ConfigDir(YNAB_DIR)
    amounts = parser.get_budget(
        'My Budget').full_budget.get_category_amounts_now()

    for category, amount in amounts.items():
        print('Category: "' + category.name + '" amount:' + str(amount))
