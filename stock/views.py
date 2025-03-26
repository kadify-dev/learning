from django.shortcuts import render, get_object_or_404, redirect

from stock.models import Stock, AccountCurrency, AccountStock
from stock.forms import BuySellForm
from django.contrib.auth.decorators import login_required
from django.core.cache import cache


def stock_list(request):
    stocks = Stock.objects.all()
    context = {
        'stocks': stocks,
    }
    return render(request, 'stocks.html', context)


@login_required
def stock_detail(request, pk):
    stock = get_object_or_404(Stock, pk=pk)

    # Проверяем, есть ли у пользователя такие акции
    has_stocks = AccountStock.objects.filter(
        account=request.user.account,
        stock=stock,
        amount__gt=0
    ).exists()

    initial = {
        'price': stock.get_random_price(),
        'action': 'sell' if has_stocks else 'buy'
    }

    context = {
        'stock': stock,
        'form': BuySellForm(initial=initial)
    }
    return render(request, 'stock.html', context)


@login_required
def stock_buy(request, pk):
    if request.method != "POST":
        return redirect('stock:detail', pk=pk)

    stock = get_object_or_404(Stock, pk=pk)
    form = BuySellForm(request.POST)

    if form.is_valid() and form.cleaned_data['action'] == 'buy':
        amount = form.cleaned_data['amount']
        price = form.cleaned_data['price']
        buy_cost = price * amount

        acc_stock, created = AccountStock.objects.get_or_create(
            account=request.user.account,
            stock=stock,
            defaults={'average_buy_cost': 0, 'amount': 0}
        )
        current_cost = acc_stock.average_buy_cost * acc_stock.amount

        total_cost = current_cost + buy_cost
        total_amount = acc_stock.amount + amount

        acc_stock.amount = total_amount
        acc_stock.average_buy_cost = total_cost / total_amount

        acc_currency, created = AccountCurrency.objects.get_or_create(
            account=request.user.account,
            currency=stock.currency,
            defaults={'amount': 0}
        )

        if acc_currency.amount < buy_cost:
            form.add_error(None, f'На счёте недостаточно средств в валюте {stock.currency.sign}')
        else:
            acc_currency.amount = acc_currency.amount - buy_cost
            acc_stock.save()
            acc_currency.save()
            return redirect('stock:account')

    context = {
        'stock': stock,
        'form': form
    }

    return render(request, 'stock.html', context)


@login_required
def account(request):
    currencies = cache.get(f'currencies_{request.user.username}')
    stocks = cache.get(f'stocks_{request.user.username}')

    if currencies is None:
        print(currencies)
        currencies = [
            {
                'amount': acc_currency.amount,
                'sign': acc_currency.currency.sign
            } for acc_currency in request.user.account.accountcurrency_set.select_related('currency')
        ]
        cache.set(f'currencies_{request.user.username}', currencies, 300)

    if stocks is None:
        stocks = [
            {
                'ticker': acc_stock.stock.ticker,
                'amount': acc_stock.amount,
                'avg': acc_stock.average_buy_cost
            } for acc_stock in request.user.account.accountstock_set.select_related('stock').all()
        ]
        cache.set(f'stocks_{request.user.username}', stocks, 300)

    context = {
        'currencies': currencies,
        'stocks': stocks
    }

    return render(request, template_name='account.html', context=context)


@login_required
def stock_sell(request, pk):
    if request.method != "POST":
        return redirect('stock:detail', pk=pk)

    stock = get_object_or_404(Stock, pk=pk)
    form = BuySellForm(request.POST)

    if form.is_valid():
        amount = form.cleaned_data['amount']
        price = form.cleaned_data['price']
        sell_cost = price * amount

        # Проверяем, есть ли у пользователя такие акции
        try:
            acc_stock = AccountStock.objects.get(account=request.user.account, stock=stock)
        except AccountStock.DoesNotExist:
            form.add_error(None, f'У вас нет акций {stock.ticker}')
            context = {
                'stock': stock,
                'form': form
            }
            return render(request, 'stock.html', context)

        # Проверяем, достаточно ли акций для продажи
        if acc_stock.amount < amount:
            form.add_error(None, f'Недостаточно акций {stock.ticker} для продажи')
        else:
            # Уменьшаем количество акций
            acc_stock.amount -= amount

            # Если продали все акции, удаляем запись
            if acc_stock.amount == 0:
                acc_stock.delete()
            else:
                acc_stock.save()

            # Пополняем валютный счет
            acc_currency, created = AccountCurrency.objects.get_or_create(
                account=request.user.account,
                currency=stock.currency,
                defaults={'amount': 0}
            )
            acc_currency.amount += sell_cost
            acc_currency.save()

            return redirect('stock:account')

    context = {
        'stock': stock,
        'form': form
    }

    return render(request, 'stock.html', context)


@login_required
def stock_trade(request, pk):
    if request.method != "POST":
        return redirect('stock:detail', pk=pk)

    form = BuySellForm(request.POST)
    if form.is_valid():
        if form.cleaned_data['action'] == 'buy':
            return stock_buy(request, pk)
        else:
            return stock_sell(request, pk)

    context = {
        'stock': get_object_or_404(Stock, pk=pk),
        'form': form
    }
    return render(request, 'stock.html', context)
