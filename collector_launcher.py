import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    from sherlock.collector_gui import main
    main()
